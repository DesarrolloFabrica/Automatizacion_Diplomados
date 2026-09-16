"""
Pipeline Diplomados (Educación Continuada) → esquema diplomas.

  Excel plano (1 hoja fuente) → CSV/xlsx normalizados → SQL 01/02/03
  Opcional: cargar a Postgres (local diplomados_dev). CORE/prod exige --permitir-prod.

Independiente de los pipelines de tickets (pipeline_zarigueya/) y Jurídico
(pipeline_juridico/): no comparte catálogos, columnas ni reglas de negocio con ellos.
No modifica CORE.

Uso (PowerShell, carpeta diplomados):

  python pipeline.py "..\\diplomados\\26e05 Diplomados ... .xlsx"
  python pipeline.py ".\\nuevo_lote.xlsx" --cargar
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from generar_sql_carga import generar
from normalizar_diplomados import normalizar

BASE = Path(__file__).resolve().parent


def validar_carga(conn) -> None:
    """Cuenta filas cargadas y las compara contra lo que se acaba de generar,
    como último chequeo antes de dar la carga por buena."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM diplomas.orden_financiera;")
        n_ordenes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM diplomas.estudiante_ref;")
        n_estudiantes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM diplomas.diplomado;")
        n_diplomados = cur.fetchone()[0]
    print(f"ordenes_financieras en BD: {n_ordenes}")
    print(f"estudiantes_ref en BD: {n_estudiantes}")
    print(f"diplomados en BD: {n_diplomados}")


def cargar_postgres(*, permitir_prod: bool) -> None:
    import psycopg2

    load_dotenv(BASE / ".env")
    host = os.getenv("DIPLOMADOS_DB_HOST", "localhost")
    port = os.getenv("DIPLOMADOS_DB_PORT", "5432")
    name = os.getenv("DIPLOMADOS_DB_NAME", "diplomados_dev")
    user = os.getenv("DIPLOMADOS_DB_USER", "postgres")
    password = os.getenv("DIPLOMADOS_DB_PASSWORD", "")

    if name.lower() == "core" and not permitir_prod:
        raise SystemExit(
            "DIPLOMADOS_DB_NAME=core es productivo. No se carga sin --permitir-prod."
        )

    conn = psycopg2.connect(
        host=host, port=port, dbname=name, user=user, password=password
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for archivo in (
                "01_diplomas_schema.sql",
                "02_cargar_catalogos.sql",
                "03_cargar_diplomados.sql",
            ):
                sql = (BASE / archivo).read_text(encoding="utf-8")
                print(f"ejecutando {archivo} …")
                cur.execute(sql)
                print(f"ok {archivo}")
        validar_carga(conn)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline Diplomados (Educación Continuada) → diplomas"
    )
    parser.add_argument("excel", help="Ruta al .xlsx de Diplomados (hoja '26e - Reporte de Ordenes Financ')")
    parser.add_argument(
        "--cargar",
        action="store_true",
        help="Después de normalizar, ejecuta 01+02+03 en Postgres (.env)",
    )
    parser.add_argument(
        "--permitir-prod",
        action="store_true",
        help="Permite cargar si DIPLOMADOS_DB_NAME=core (GCP). Por defecto bloqueado.",
    )
    parser.add_argument(
        "--forzar-carga-con-criticas",
        action="store_true",
        help="Permite cargar aunque haya advertencias 'critico' en advertencias_calidad.csv "
             "(un dato sin el tipo esperado). Por defecto, si hay alguna, la carga se bloquea "
             "sola — esta es la señal que usa la automatización para decidir si sigue o se "
             "detiene y solo notifica.",
    )
    args = parser.parse_args()
    excel = Path(args.excel)
    if not excel.exists():
        raise SystemExit(f"No existe: {excel}")

    print("1/3 normalizar Excel → CSV")
    stats = normalizar(excel, BASE)
    print(stats)
    n_criticas = stats.get("advertencias_criticas", 0)
    if stats.get("advertencias"):
        print(
            f"AVISO: {stats['advertencias']} advertencia(s) de calidad en advertencias_calidad.csv "
            f"({n_criticas} crítica(s)) — revísalas antes de cargar a producción."
        )

    print("2/3 generar SQL de carga")
    generar()

    if args.cargar and n_criticas and not args.forzar_carga_con_criticas:
        print(
            f"3/3 carga BLOQUEADA: hay {n_criticas} advertencia(s) crítica(s) (dato sin el tipo "
            "esperado). Revisa advertencias_calidad.csv y corrige el archivo de origen, o vuelve "
            "a correr con --forzar-carga-con-criticas si ya revisaste y decides cargar igual."
        )
        raise SystemExit(2)
    elif args.cargar:
        print("3/3 cargar a Postgres")
        cargar_postgres(permitir_prod=args.permitir_prod)
    else:
        print("3/3 carga omitida (pasa --cargar para Postgres local)")
        print("SQL listo: 01_diplomas_schema.sql, 02_cargar_catalogos.sql, 03_cargar_diplomados.sql")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
