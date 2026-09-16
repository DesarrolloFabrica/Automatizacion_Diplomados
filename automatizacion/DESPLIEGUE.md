# Despliegue de la automatización de Diplomados (Fase 2)

Esto convierte el piloto ya validado (carpeta `diplomados/` en tu PC — antes se llamaba
`pipeline_diplomados/`, se renombró el 4 sep 2026 al organizar carpetas; modo acumular) en un
proceso que corre solo cada lunes 9am, revisando `DATOS/diplomados/` en Drive. Corre estos
comandos tú mismo desde tu terminal (con `gcloud` autenticado contra tu proyecto), en el
mismo orden — igual que corriste el SQL en pgAdmin.

Nota: en Cloud Shell (la nube) la carpeta sigue llamándose `~/pipeline_diplomados/` — ese
renombrado fue solo local, en tu PC, no se tocó lo ya subido a Cloud Shell. Si en el futuro
subes un archivo modificado (como hicimos con `sync_diplomados.py`), síguelo subiendo dentro
de esa carpeta `~/pipeline_diplomados/` en Cloud Shell, aunque en tu PC ahora se llame
`diplomados/`.

Reemplaza los valores entre `<...>` por los tuyos antes de copiar/pegar cada bloque.

## Progreso de esta sesión (3 sep 2026) — valores reales ya recolectados

| Dato | Valor |
|---|---|
| Proyecto | `it-fab-contenido-edu-6` |
| Región | `us-central1` |
| Instancia (conexión) | `it-fab-contenido-edu-6:us-central1:core-database` |
| Carpeta Drive `DATOS/diplomados/` | `1fPQOESznANRhsomQTcZ6ykV3SAxWR4Ei` |
| Correo de aviso | `angie_vera@cun.edu.co` |
| Usuario BD | `user-core` |
| IP pública de `core-database` | `136.113.128.135` |
| IP fija del robot (`diplomados-nat-ip`) | `35.239.233.158` — ya agregada a redes autorizadas ✅ |

Ya completado en Cloud Shell: APIs habilitadas (paso 0), cuenta de servicio
`diplomados-sync` creada (paso 1), IP fija + conector VPC + router/NAT creados (paso 1b).
`roles/cloudsql.client` NO se consiguió (bloqueado por el equipo de infraestructura) — se
resolvió con el camino de IP fija en su lugar.

Pendiente: Secret Manager (paso 2), construir imagen (paso 3), crear el Cloud Run Job
(paso 4), Cloud Scheduler (paso 5), primera prueba (paso 6). Notificación por correo
(SMTP) sigue en pausa — se puede dejar `NOTIFY_EMAIL_TO` sin `SMTP_USER`/`SMTP_PASSWORD`
por ahora; el script solo imprime el resumen en los logs si no hay SMTP configurado.

```powershell
$PROJECT_ID   = "<tu-project-id-de-gcp>"
$REGION       = "<ej. us-central1>"
$SQL_INSTANCE = "<connection-name-de-tu-Cloud-SQL, formato project:region:instancia>"
$DRIVE_FOLDER_ID = "<id de la carpeta DATOS/diplomados/ en Drive>"
$NOTIFY_TO    = "<tu correo, el que recibe el aviso>"
```

## 0. Habilitar las APIs necesarias (una sola vez)

```powershell
gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com `
    drive.googleapis.com secretmanager.googleapis.com sqladmin.googleapis.com
```

## 1. Crear la cuenta de servicio del robot

```powershell
gcloud iam service-accounts create diplomados-sync `
    --display-name="Diplomados - sync automático Drive -> diplomas"
```

Para Drive: como Drive no usa roles de GCP sino permisos de la propia carpeta, hay que
**compartir la carpeta `DATOS/diplomados/` con el correo de esta cuenta de servicio**
(`diplomados-sync@<PROJECT_ID>.iam.gserviceaccount.com`) como "Lector", igual que
compartirías la carpeta con una persona más.

### 1b. Conexión a Cloud SQL: IP fija en vez de `roles/cloudsql.client`

El camino "normal" para que Cloud Run se conecte a Cloud SQL es con el permiso
`roles/cloudsql.client` (túnel privado de Google). En nuestro caso, esa área no dio ese
permiso todavía, así que el robot se conecta **igual que pgAdmin**: por IP pública +
usuario + contraseña, agregando una IP fija propia a las "redes autorizadas" de la
instancia. Si más adelante consiguen el permiso `roles/cloudsql.client`, este bloque
completo (1b) se puede saltar y usar `--set-cloudsql-instances` en el paso 4 en su lugar.

```powershell
# 1) Reservar una IP fija para el robot
gcloud compute addresses create diplomados-nat-ip --region=$REGION

# 2) Camino privado de salida (conector VPC) para el robot
gcloud services enable vpcaccess.googleapis.com
gcloud compute networks vpc-access connectors create diplomados-connector `
    --region=$REGION `
    --network=default `
    --range=10.8.0.0/28

# 3) Router + Cloud NAT: hace que todo lo que sale por el conector use la IP fija
gcloud compute routers create diplomados-router --network=default --region=$REGION
gcloud compute routers nats create diplomados-nat `
    --router=diplomados-router --region=$REGION `
    --nat-external-ip-pool=diplomados-nat-ip --nat-all-subnet-ip-ranges

# 4) Ver el número de la IP fija que quedó reservada
gcloud compute addresses describe diplomados-nat-ip --region=$REGION --format="value(address)"
```

Con ese número: entra a la consola web → SQL → `core-database` → "Conexiones" → "Redes" →
"Agregar una red" → pega la IP con `/32` al final (ej. `35.239.233.158/32`) → Guardar.
Esto lo hace cualquiera con acceso de edición a la instancia (no requiere el permiso de
IAM que estaba bloqueado — son dos cosas distintas).

También anota la **IP pública de la propia instancia** (pestaña "Resumen" de
`core-database`) — la vas a necesitar en el paso 4 como `DIPLOMADOS_DB_HOST`.

## 2. Guardar los secretos (contraseña de BD + credenciales del correo)

```powershell
echo "<password de DIPLOMADOS_DB_USER>" | gcloud secrets create diplomados-db-password --data-file=-
echo "<contraseña de aplicación de Gmail>" | gcloud secrets create diplomados-smtp-password --data-file=-

gcloud secrets add-iam-policy-binding diplomados-db-password `
    --member="serviceAccount:diplomados-sync@$PROJECT_ID.iam.gserviceaccount.com" `
    --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding diplomados-smtp-password `
    --member="serviceAccount:diplomados-sync@$PROJECT_ID.iam.gserviceaccount.com" `
    --role="roles/secretmanager.secretAccessor"
```

La "contraseña de aplicación de Gmail" NO es tu contraseña normal — se genera en
myaccount.google.com → Seguridad → Contraseñas de aplicaciones (necesita verificación en
2 pasos activada en esa cuenta de Gmail).

## 3. Construir la imagen (desde la carpeta `pipeline_diplomados/`, OJO con el contexto)

```powershell
cd "FLUJO\pipeline_diplomados"
$IMAGE = "$REGION-docker.pkg.dev/$PROJECT_ID/diplomados/sync:latest"

# si es la primera vez, crea el repositorio de Artifact Registry:
gcloud artifacts repositories create diplomados --repository-format=docker --location=$REGION

gcloud builds submit --config=automatizacion/cloudbuild.yaml --substitutions=_IMAGE=$IMAGE .
```

(si no usas Artifact Registry, cambia `$IMAGE` a `gcr.io/$PROJECT_ID/diplomados-sync` y omite el paso de crear el repositorio).

## 4. Crear el Cloud Run Job

```powershell
$DB_HOST = "<IP pública de core-database, ej. 136.113.128.135>"

gcloud run jobs create diplomados-sync `
    --image=$IMAGE `
    --region=$REGION `
    --service-account="diplomados-sync@$PROJECT_ID.iam.gserviceaccount.com" `
    --vpc-connector=diplomados-connector `
    --vpc-egress=all-traffic `
    --set-env-vars="DRIVE_FOLDER_ID=$DRIVE_FOLDER_ID,DIPLOMADOS_DB_HOST=$DB_HOST,DIPLOMADOS_DB_NAME=core,DIPLOMADOS_DB_USER=<usuario_db>,NOTIFY_EMAIL_TO=$NOTIFY_TO,SMTP_USER=<correo_remitente@gmail.com>" `
    --set-secrets="DIPLOMADOS_DB_PASSWORD=diplomados-db-password:latest,SMTP_PASSWORD=diplomados-smtp-password:latest" `
    --max-retries=1 `
    --task-timeout=900
```

`--vpc-connector` + `--vpc-egress=all-traffic` es lo que obliga a que TODO lo que el robot
intente conectar hacia afuera (incluida la base) pase por el conector → Cloud NAT → salga
con la IP fija que ya autorizamos en el paso 1b. Sin `--vpc-egress=all-traffic`, el tráfico
hacia una IP pública normal seguiría saliendo por una IP aleatoria, no por la fija.

Nota de seguridad: `DIPLOMADOS_DB_NAME=core` aquí es intencional (el robot SÍ debe cargar
al esquema `diplomas` dentro de la base compartida `core`) — la guarda `--permitir-prod`
de `pipeline.py` no aplica a este script (es un flujo separado, pensado para producción
desde el diseño, con su propio freno: la advertencia crítica). Si algún día quieres una
base de prueba separada para este job, cambia `DIPLOMADOS_DB_NAME` y `$DB_HOST`.

## 5. Crear el disparador (Cloud Scheduler, cada lunes 9am hora Bogotá)

```powershell
gcloud scheduler jobs create http diplomados-sync-semanal `
    --location=$REGION `
    --schedule="0 9 * * 1" `
    --time-zone="America/Bogota" `
    --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/diplomados-sync:run" `
    --http-method=POST `
    --oauth-service-account-email="diplomados-sync@$PROJECT_ID.iam.gserviceaccount.com"
```

## 6. Probarlo ya, sin esperar al lunes

```powershell
gcloud run jobs execute diplomados-sync --region=$REGION
```

Revisa los logs:
```powershell
gcloud run jobs executions list --job=diplomados-sync --region=$REGION
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=diplomados-sync" --limit=50
```

## Qué revisar la primera vez

1. Sube manualmente el Excel real a `DATOS/diplomados/` en Drive (o deja el que ya está, si
   la carpeta se creó a partir de él).
2. Corre el paso 6 (ejecución manual).
3. Debe llegarte un correo a `$NOTIFY_TO` diciendo cuántas órdenes se cargaron.
4. Verifica en pgAdmin: `SELECT * FROM diplomas.archivo_procesado ORDER BY procesado_en DESC;`
   — debe aparecer el archivo con estado `cargado`.
5. Vuelve a correr el paso 6 sin cambiar nada en Drive: debe decir "sin archivos nuevos"
   (no debe volver a cargar ni duplicar).
