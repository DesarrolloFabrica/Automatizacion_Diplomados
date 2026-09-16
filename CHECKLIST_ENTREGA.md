# Checklist de entrega — Diplomados

Marcar antes de dar por cerrado un despliegue o una entrega del flujo.

## A. Documentación

- [ ] Existe `DOCUMENTACION_PROCESO.md` (workflow + fases)
- [ ] Existe `DICCIONARIO_DATOS_EXCEL.md`
- [ ] Existe `LEEME.txt` (piloto local)
- [ ] Existe `automatizacion/DESPLIEGUE.md` (GCP)
- [ ] README del repo apunta a esos docs

## B. Piloto local (Fase 1)

- [ ] `pip install -r requirements.txt` OK
- [ ] `.env` creado desde `.env.example` (no se sube al repo)
- [ ] Normalizar con un Excel de prueba que tenga hoja `26e - Reporte de Ordenes Financ`
- [ ] `pipeline.py` genera `02` y `03` sin error
- [ ] Carga a base **local** de prueba OK (modo acumular)
- [ ] Revisar `advertencias_calidad.csv` (crítico vs info)

## C. Automatización nube (Fase 2)

- [ ] Cuenta de servicio creada y carpeta Drive compartida (lector)
- [ ] Secretos en Secret Manager (sin contraseñas en código)
- [ ] Cloud Run Job creado y prueba manual OK
- [ ] Cloud Scheduler (lunes ~9am Bogotá) configurado
- [ ] Correo de aviso llega a los destinatarios acordados
- [ ] Un archivo ya procesado **no** se vuelve a cargar (idempotencia)

## D. Validación funcional

- [ ] Conteo de órdenes coherente con el Excel
- [ ] Estudiantes en `estudiante_ref`; muestra de match con `core.person` (`04a_...sql`)
- [ ] UPSERT: segunda corrida del mismo archivo no duplica
- [ ] Archivo con hoja mal nombrada: **no** carga y avisa por correo/log

## E. Seguridad / repo

- [ ] No hay `.env` ni credenciales en Git
- [ ] `.gitignore` incluye `__pycache__/`, `.env`, salidas temporales, Excel con datos personales si aplica
- [ ] Producción solo con `--permitir-prod` o vía el Job (no a mano sin autorización)

## Firma de cierre

| Campo | Valor |
|-------|-------|
| Fecha | |
| Responsable | |
| Observaciones | |
