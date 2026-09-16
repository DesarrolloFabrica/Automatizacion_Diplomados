<div align="center">

# Automatización Diplomados

**CUN · Fábrica de contenidos** — Excel de órdenes financieras → Postgres (`diplomas`) + robot semanal en GCP

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-esquema%20diplomas-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Google Cloud](https://img.shields.io/badge/Google%20Cloud-Run%20%2B%20Scheduler-4285F4?logo=googlecloud&logoColor=white)](https://cloud.google.com/)
[![Drive](https://img.shields.io/badge/Google%20Drive-fuente%20Excel-0F9D58?logo=googledrive&logoColor=white)](https://drive.google.com/)
[![Licencia](https://img.shields.io/badge/Uso-interno%20CUN-orange)](#)

</div>

---

## Tabla de contenido

- [Visión general](#-visión-general)
- [Qué es (y qué no es)](#-qué-es-y-qué-no-es)
- [Documentación](#-documentación)
- [Uso rápido (local)](#-uso-rápido-local)
- [Flujo continuo](#-flujo-continuo)
- [Estructura del proyecto](#-estructura-del-proyecto)
- [Requisitos](#-requisitos)

---

## Visión general

Pipeline de **Educación Continuada / Diplomados**: toma el Excel semanal de órdenes financieras, lo normaliza, cruza estudiantes con `core.person` (por documento) y carga en modo **acumular** (UPSERT).

| Fase | Dónde | Qué hace |
|------|--------|----------|
| **Fase 1** | PC | Piloto / prueba con `pipeline.py` |
| **Fase 2** | GCP | Robot cada lunes ~9am (`sync_diplomados.py`) |

Hoja Excel obligatoria: **`26e - Reporte de Ordenes Financ`**.

---

## Qué es (y qué no es)

| Esto sí | Esto no |
|---------|---------|
| Carga de diplomados / órdenes | Flujo LMS / Inventario |
| Cruce estudiante → `core.person` | Informe `Pendientes_Cruce_CORE` |
| Robot lunes Drive → BD | Consultorio Jurídico ([repo aparte](https://github.com/DesarrolloFabrica/Automatizacion_Juridico)) |

---

## Documentación

| Doc | Para qué |
|-----|----------|
| [DOCUMENTACION_PROCESO.md](DOCUMENTACION_PROCESO.md) | Workflow paso a paso |
| [DICCIONARIO_DATOS_EXCEL.md](DICCIONARIO_DATOS_EXCEL.md) | Hojas y columnas |
| [CHECKLIST_ENTREGA.md](CHECKLIST_ENTREGA.md) | Validar que la entrega quedó cerrada |
| [automatizacion/DESPLIEGUE.md](automatizacion/DESPLIEGUE.md) | Comandos GCP (Fase 2) |

---

## Uso rápido (local)

```bash
pip install -r requirements.txt
copy .env.example .env

# Solo normalizar + generar SQL
python pipeline.py "RUTA\26e05 Diplomados ....xlsx"

# Cargar a Postgres local (pruebas)
python pipeline.py "RUTA\26e05 Diplomados ....xlsx" --cargar
```

Producción GCP solo con autorización (`--permitir-prod` o el Job de Cloud Run).

El esquema (`01_diplomas_schema.sql`) **no** forma parte del flujo diario: solo si la base es nueva.

---

## Flujo continuo

Un solo orquestador encadena los pasos:

```
Excel → normalizar → generar SQL → (cargar) → registrar / correo
```

- Local: `pipeline.py`
- Nube: `automatizacion/sync_diplomados.py` (Scheduler → Cloud Run)

---

## Estructura del proyecto

```
Automatizacion_Diplomados/
├── README.md
├── DOCUMENTACION_PROCESO.md
├── DICCIONARIO_DATOS_EXCEL.md
├── CHECKLIST_ENTREGA.md
├── normalizar_diplomados.py
├── generar_sql_carga.py
├── pipeline.py
├── 01_diplomas_schema.sql          # una vez (ambiente nuevo)
├── 04a_verificar_match_core_person.sql
├── requirements.txt
├── .env.example
└── automatizacion/
    ├── sync_diplomados.py
    ├── DESPLIEGUE.md
    ├── Dockerfile
    └── cloudbuild.yaml
```

---

## Requisitos

- Python 3.10+
- PostgreSQL (local para pruebas)
- Fase 2: proyecto GCP, Drive, Secret Manager, Cloud Run + Scheduler
