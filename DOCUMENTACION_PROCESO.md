# Documentación del proceso — Diplomados (Educación Continuada)

CUN · Fábrica de contenidos · sep 2026

Este documento describe el **workflow completo**: desde el Excel en Drive hasta la carga en Postgres (`esquema diplomas`) y el robot automático (Fase 2).

Relacionado:

- `LEEME.txt` — guía del piloto local (Fase 1)
- `automatizacion/DESPLIEGUE.md` — comandos GCP (Fase 2)
- `CHECKLIST_ENTREGA.md` — validación de cierre
- `DICCIONARIO_DATOS_EXCEL.md` — columnas del Excel

---

## 1. Qué problema resuelve

Cada semana llegan Excel de **órdenes financieras** de diplomados. El proceso:

1. Lee el archivo (hoja de órdenes).
2. Normaliza a catálogos + hecho `orden_financiera`.
3. Cruza estudiantes con `core.person` (documento primero, nombre de respaldo).
4. Carga en modo **acumular** (UPSERT: no borra lo anterior).
5. En Fase 2, el robot en la nube hace esto solo cada lunes y avisa por correo.

**No** es el flujo LMS/Inventario ni el informe de pendientes CORE. Es un pipeline aparte.

---

## 2. Fases

| Fase | Dónde | Qué es |
|------|--------|--------|
| **Fase 1 — Piloto** | PC (`pipeline.py`) | Validar normalización y carga manual/local |
| **Fase 2 — Automático** | GCP (Cloud Run Job + Scheduler) | Cada lunes ~9am revisa Drive y carga |

---

## 3. Workflow (flujo continuo)

### Fase 1 (local, a demanda)

```
Excel .xlsx
    -> normalizar_diplomados.py
    -> CSV / xlsx normalizado
    -> generar_sql_carga.py
    -> 02_cargar_catalogos.sql + 03_cargar_diplomados.sql
    -> (opcional) pipeline.py --cargar  -> Postgres
```

Orquestador local: `pipeline.py` encadena normalizar → generar SQL → cargar (si se pide).

### Fase 2 (nube, automático)

```
Cloud Scheduler (lunes 9am)
    -> Cloud Run Job
        -> sync_diplomados.py
            1. Lista archivos en Drive DATOS/diplomados/
            2. Omite los ya procesados (diplomas.archivo_procesado)
            3. Descarga cada Excel nuevo
            4. Llama normalizar() + generar SQL (mismo código Fase 1)
            5. Si hay advertencias "critico" -> NO carga; marca bloqueado
            6. Si OK -> ejecuta UPSERT en Postgres
            7. Registra archivo y envía correo de resumen
```

Encadenamiento: **un solo job** (`sync_diplomados.py`) ejecuta todos los pasos en secuencia. No hace falta lanzar scripts a mano en producción.

---

## 4. Requisitos del Excel

- Debe existir la hoja exacta: **`26e - Reporte de Ordenes Financ`**
- Otras hojas (resúmenes / ventas) se **ignoran**
- Si el nombre de hoja cambia, el robot falla y avisa por correo (ejemplo: archivos del 14 sep 2026)

Detalle de columnas: `DICCIONARIO_DATOS_EXCEL.md`

---

## 5. Base de datos

- Esquema: `diplomas` (en la instancia CORE de GCP)
- Modo: **acumular** (INSERT … ON CONFLICT … DO UPDATE)
- El script `01_diplomas_schema.sql` crea tablas con `IF NOT EXISTS`
  - En el **flujo diario automático ya no se recrea el esquema**; solo se usa si la base es nueva
- Verificación de cruce: `04a_verificar_match_core_person.sql` (solo lectura)

---

## 6. Cómo correr (resumen)

### Local (Fase 1)

```bash
pip install -r requirements.txt
copy .env.example .env   # completar conexión local

python normalizar_diplomados.py "RUTA\archivo.xlsx"
python pipeline.py "RUTA\archivo.xlsx"
python pipeline.py "RUTA\archivo.xlsx" --cargar
# Producción solo con autorización:
python pipeline.py "RUTA\archivo.xlsx" --cargar --permitir-prod
```

### Nube (Fase 2)

Ver `automatizacion/DESPLIEGUE.md` (cuenta de servicio, Secret Manager, Cloud Run Job, Scheduler).

---

## 7. Correo de aviso

Asunto típico: *Diplomados — carga automática semanal*.

Incluye archivos nuevos y errores (ej. hoja con nombre incorrecto). Destinatarios vía `NOTIFY_EMAIL_TO`.

---

## 8. Límites conocidos

- Teléfonos con formato irregular → advertencia `info` (no bloquea)
- Fila sin diplomado / datos críticos → advertencia `critico` (bloquea carga de ese archivo)
- No toca esquemas `core`, `legal_consulting`, ni tickets

---

## 9. Mapa de archivos clave

| Archivo | Rol |
|---------|-----|
| `normalizar_diplomados.py` | Lee Excel → CSV |
| `generar_sql_carga.py` | CSV → SQL 02/03 |
| `pipeline.py` | Orquesta Fase 1 |
| `automatizacion/sync_diplomados.py` | Orquesta Fase 2 |
| `01_diplomas_schema.sql` | Crear tablas (una vez) |
| `04a_verificar_match_core_person.sql` | Validar cruce CORE |
| `ERD_diplomas.html` / `diplomas.dbml` | Diagrama |
