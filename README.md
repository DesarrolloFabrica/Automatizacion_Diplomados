# Automatización Diplomados (Educación Continuada)

Pipeline CUN · Fábrica de contenidos: Excel de órdenes financieras → Postgres (`esquema diplomas`), con robot semanal en GCP.

## Qué es (y qué no es)

| Esto sí | Esto no |
|---------|---------|
| Carga de diplomados / órdenes | Flujo LMS / Inventario (`Atutomatizacion_Inventario`) |
| Cruce estudiante → `core.person` | Informe de pendientes (`Pendientes_Cruce_CORE`) |
| Robot lunes en Drive → BD | Consultorio Jurídico (repo aparte) |

## Docs (empieza aquí)

1. [DOCUMENTACION_PROCESO.md](DOCUMENTACION_PROCESO.md) — workflow paso a paso  
2. [DICCIONARIO_DATOS_EXCEL.md](DICCIONARIO_DATOS_EXCEL.md) — hojas y columnas  
3. [CHECKLIST_ENTREGA.md](CHECKLIST_ENTREGA.md) — validar entrega  
4. [LEEME.txt](LEEME.txt) — piloto local detallado  
5. [automatizacion/DESPLIEGUE.md](automatizacion/DESPLIEGUE.md) — Fase 2 en GCP  

## Uso rápido (local)

```bash
pip install -r requirements.txt
copy .env.example .env

python pipeline.py "RUTA\26e05 Diplomados ....xlsx"
python pipeline.py "RUTA\26e05 Diplomados ....xlsx" --cargar
```

La hoja obligatoria es: `26e - Reporte de Ordenes Financ`.

## Estructura

```
diplomados/
  normalizar_diplomados.py
  generar_sql_carga.py
  pipeline.py
  01_diplomas_schema.sql
  04a_verificar_match_core_person.sql
  automatizacion/          # Fase 2 (Cloud Run)
    sync_diplomados.py
    DESPLIEGUE.md
    Dockerfile
  DOCUMENTACION_PROCESO.md
  DICCIONARIO_DATOS_EXCEL.md
  CHECKLIST_ENTREGA.md
```

## Requisitos

- Python 3.10+
- Postgres (local para pruebas; GCP para producción autorizada)
- Para Fase 2: proyecto GCP, Drive, Secret Manager
