"""Genera 02_cargar_catalogos.sql y 03_cargar_diplomados.sql a partir de los CSV
normalizados por normalizar_diplomados.py.

MODO ACUMULAR (piloto de automatización, sep 2026): a diferencia de la primera versión
(que hacía TRUNCATE + recarga completa con ids fijos), esta versión genera
INSERT ... ON CONFLICT ... DO UPDATE (UPSERT):
  - Si la llave natural (código de catálogo, documento del estudiante, número de orden)
    ya existe en la base, ACTUALIZA sus columnas.
  - Si no existe, la INSERTA como fila nueva.
  - Nunca borra nada. Se puede correr muchas veces sin duplicar (es idempotente).

Las relaciones (FK) se resuelven con subconsultas por código (ej.
"SELECT id FROM diplomas.diplomado WHERE codigo = 'CE510'") en vez de ids fijos, así
funciona igual en la primera carga que acumulando sobre datos ya existentes: no importa
qué id real le haya asignado Postgres a cada catálogo, la subconsulta siempre lo encuentra.

Excepción a propósito: estudiante_ref.core_person_id y match_status NUNCA se tocan en el
UPDATE (los llena un proceso de verificación aparte, 04a_verificar_match_core_person.sql;
si el UPSERT los reescribiera, cada recarga semanal borraría el trabajo manual de cruce
contra CORE).
"""

from __future__ import annotations

import csv
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_CAT = BASE / "02_cargar_catalogos.sql"
OUT_HECHOS = BASE / "03_cargar_diplomados.sql"


def sql_str(value: str | None) -> str:
    if value is None or value == "":
        return "NULL"
    tag = "ce"
    n = 0
    while f"${tag}$" in value:
        n += 1
        tag = f"ce{n}"
    return f"${tag}${value}${tag}$"


def sql_int(value: str | None) -> str:
    if value is None or str(value).strip() == "":
        return "NULL"
    return str(int(str(value).strip()))


def sql_num(value: str | None) -> str:
    if value is None or str(value).strip() == "":
        return "NULL"
    return str(float(str(value).strip()))


def sql_date(value: str | None) -> str:
    if value is None or str(value).strip() == "":
        return "NULL"
    return f"DATE {sql_str(str(value).strip())}"


def rows_of(name: str) -> list[dict[str, str]]:
    path = BASE / name
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def generar(base_dir: str | Path | None = None) -> None:
    """Genera 02/03 leyendo los CSV de base_dir (o de la carpeta de este archivo, si no
    se pasa nada -- uso normal por línea de comandos). Pensado para reutilizarse desde
    automatizacion/sync_diplomados.py, que normaliza cada archivo de Drive en su propia
    carpeta temporal y llama generar(base_dir=esa_carpeta)."""
    global BASE, OUT_CAT, OUT_HECHOS
    if base_dir is not None:
        BASE = Path(base_dir)
        OUT_CAT = BASE / "02_cargar_catalogos.sql"
        OUT_HECHOS = BASE / "03_cargar_diplomados.sql"

    lines: list[str] = [
        "-- Carga (UPSERT) de catálogos del Excel normalizado a diplomas.",
        "-- Ejecutar DESPUÉS de 01_diplomas_schema.sql.",
        "-- MODO ACUMULAR: no borra nada. Código existente -> actualiza; código nuevo -> inserta.",
        "-- Idempotente: correrlo varias veces con el mismo archivo no duplica ni daña nada.",
        "BEGIN;",
        "",
    ]

    for row in rows_of("periodo_academico.csv"):
        lines.append(
            "INSERT INTO diplomas.periodo_academico (codigo) VALUES "
            f"({sql_str(row['codigo'])}) ON CONFLICT (codigo) DO NOTHING;"
        )
    lines.append("")

    for row in rows_of("diplomado.csv"):
        lines.append(
            "INSERT INTO diplomas.diplomado (codigo, nombre) VALUES "
            f"({sql_str(row['codigo'])}, {sql_str(row['nombre'])}) "
            "ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre;"
        )
    lines.append("")

    for tabla in ("sede", "seccional", "modalidad", "jornada"):
        for row in rows_of(f"{tabla}.csv"):
            lines.append(
                f"INSERT INTO diplomas.{tabla} (codigo, nombre) VALUES "
                f"({sql_int(row['codigo'])}, {sql_str(row['nombre'])}) "
                "ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre;"
            )
        lines.append("")

    for row in rows_of("estado_pago.csv"):
        lines.append(
            "INSERT INTO diplomas.estado_pago (nombre) VALUES "
            f"({sql_str(row['nombre'])}) ON CONFLICT (nombre) DO NOTHING;"
        )
    lines.append("")

    for row in rows_of("clasificacion_contable.csv"):
        lines.append(
            "INSERT INTO diplomas.clasificacion_contable (fondo_codigo, fondo_nombre, producto, fuente) VALUES "
            f"({sql_int(row['fondo_codigo'])}, {sql_str(row['fondo_nombre'])}, "
            f"{sql_str(row['producto'])}, {sql_str(row['fuente'])}) "
            "ON CONFLICT (fondo_codigo, producto, fuente) DO UPDATE SET fondo_nombre = EXCLUDED.fondo_nombre;"
        )
    lines.append("")

    for row in rows_of("estudiante_ref.csv"):
        lines.append(
            "INSERT INTO diplomas.estudiante_ref (documento_origen, tipo_documento_origen, "
            "id_tercero_origen, nombres, segundo_nombre, apellido1, apellido2, "
            "nombre_completo_normalizado, genero, fecha_nacimiento, fecha_expedicion_documento, "
            "email_institucional, email_personal, telefono_casa, telefono_celular, direccion) VALUES ("
            f"{sql_str(row['documento_origen'])}, {sql_str(row['tipo_documento_origen'])}, "
            f"{sql_int(row['id_tercero_origen'])}, {sql_str(row['nombres'])}, {sql_str(row['segundo_nombre'])}, "
            f"{sql_str(row['apellido1'])}, {sql_str(row['apellido2'])}, "
            f"{sql_str(row['nombre_completo_normalizado'])}, {sql_str(row['genero'])}, "
            f"{sql_date(row['fecha_nacimiento'])}, {sql_date(row['fecha_expedicion_documento'])}, "
            f"{sql_str(row['email_institucional'])}, {sql_str(row['email_personal'])}, "
            f"{sql_str(row['telefono_casa'])}, {sql_str(row['telefono_celular'])}, {sql_str(row['direccion'])}"
            ") ON CONFLICT (documento_origen) DO UPDATE SET "
            "tipo_documento_origen = EXCLUDED.tipo_documento_origen, "
            "id_tercero_origen = EXCLUDED.id_tercero_origen, "
            "nombres = EXCLUDED.nombres, segundo_nombre = EXCLUDED.segundo_nombre, "
            "apellido1 = EXCLUDED.apellido1, apellido2 = EXCLUDED.apellido2, "
            "nombre_completo_normalizado = EXCLUDED.nombre_completo_normalizado, "
            "genero = EXCLUDED.genero, fecha_nacimiento = EXCLUDED.fecha_nacimiento, "
            "fecha_expedicion_documento = EXCLUDED.fecha_expedicion_documento, "
            "email_institucional = EXCLUDED.email_institucional, "
            "email_personal = EXCLUDED.email_personal, telefono_casa = EXCLUDED.telefono_casa, "
            "telefono_celular = EXCLUDED.telefono_celular, direccion = EXCLUDED.direccion, "
            "updated_at = now();"
            "  -- core_person_id y match_status NO se tocan a propósito (ver docstring de este archivo)"
        )
    lines.append("")
    lines.append("COMMIT;")
    lines.append("")
    OUT_CAT.write_text("\n".join(lines), encoding="utf-8")

    hechos: list[str] = [
        "-- Carga (UPSERT) del hecho orden_financiera. Ejecutar DESPUÉS de 02_cargar_catalogos.sql.",
        "-- MODO ACUMULAR: no borra nada. Orden existente -> actualiza sus valores (ej. cambio de",
        "-- estado de pago); Orden nueva -> la inserta. Idempotente.",
        "BEGIN;",
        "",
    ]
    lines = hechos

    for row in rows_of("orden_financiera.csv"):
        estudiante_sub = f"(SELECT id FROM diplomas.estudiante_ref WHERE documento_origen = {sql_str(row['estudiante_documento'])})"
        periodo_sub = f"(SELECT id FROM diplomas.periodo_academico WHERE codigo = {sql_str(row['periodo_codigo'])})"
        diplomado_sub = f"(SELECT id FROM diplomas.diplomado WHERE codigo = {sql_str(row['diplomado_codigo'])})"
        sede_sub = f"(SELECT id FROM diplomas.sede WHERE codigo = {sql_int(row['sede_codigo'])})"
        seccional_sub = f"(SELECT id FROM diplomas.seccional WHERE codigo = {sql_int(row['seccional_codigo'])})"
        modalidad_sub = f"(SELECT id FROM diplomas.modalidad WHERE codigo = {sql_int(row['modalidad_codigo'])})"
        jornada_sub = f"(SELECT id FROM diplomas.jornada WHERE codigo = {sql_int(row['jornada_codigo'])})"
        clasif_sub = (
            "(SELECT id FROM diplomas.clasificacion_contable WHERE fondo_codigo = "
            f"{sql_int(row['clasif_fondo_codigo'])} AND producto = {sql_str(row['clasif_producto'])} "
            f"AND fuente = {sql_str(row['clasif_fuente'])})"
        )
        estado_aca_sub = f"(SELECT id FROM diplomas.estado_pago WHERE nombre = {sql_str(row['estado_pago_academico_nombre'])})"
        estado_fin_sub = f"(SELECT id FROM diplomas.estado_pago WHERE nombre = {sql_str(row['estado_pago_financiero_nombre'])})"

        lines.append(
            "INSERT INTO diplomas.orden_financiera ("
            "orden_externa, estudiante_id, periodo_id, diplomado_id, sede_id, seccional_id, "
            "modalidad_id, jornada_id, clasificacion_contable_id, estado_pago_academico_id, "
            "estado_pago_financiero_id, tipo_inscripcion, fecha_creacion_academica, "
            "fecha_creacion_financiera, fecha_pago_liquidacion, fecha_recibo, fecha_siguiente_pago, "
            "fecha_pago_anterior, periodo_ultimo_pago_texto, valor_orden, valor_liquidado, "
            "valor_pagado, valor_pago_directo, saldo_favor, valor_credito, valor_icetex, "
            "valor_contratos, valor_becas_descuentos, valor_otras_notas_credito, "
            "valor_nota_credito_anulacion, valor_tarjeta_debito, valor_tarjeta_credito, "
            "valor_pago_banco, valor_efectivo, valor_place, valor_2x1, creditos_orden, "
            "referencia_liquidacion, grupo_facturacion_codigo, descripcion_grupo_facturacion, "
            "ubicacion_texto, formulario_texto, numero_formulario, creado_por_texto, "
            "actualizado_por_texto, sistema_origen"
            ") VALUES ("
            f"{sql_int(row['orden_externa'])}, {estudiante_sub}, {periodo_sub}, {diplomado_sub}, "
            f"{sede_sub}, {seccional_sub}, {modalidad_sub}, {jornada_sub}, {clasif_sub}, "
            f"{estado_aca_sub}, {estado_fin_sub}, "
            f"{sql_str(row['tipo_inscripcion'])}, {sql_date(row['fecha_creacion_academica'])}, "
            f"{sql_date(row['fecha_creacion_financiera'])}, {sql_date(row['fecha_pago_liquidacion'])}, "
            f"{sql_date(row['fecha_recibo'])}, {sql_date(row['fecha_siguiente_pago'])}, "
            f"{sql_date(row['fecha_pago_anterior'])}, {sql_str(row['periodo_ultimo_pago_texto'])}, "
            f"{sql_num(row['valor_orden'])}, {sql_num(row['valor_liquidado'])}, {sql_num(row['valor_pagado'])}, "
            f"{sql_num(row['valor_pago_directo'])}, {sql_num(row['saldo_favor'])}, {sql_num(row['valor_credito'])}, "
            f"{sql_num(row['valor_icetex'])}, {sql_num(row['valor_contratos'])}, {sql_num(row['valor_becas_descuentos'])}, "
            f"{sql_num(row['valor_otras_notas_credito'])}, {sql_num(row['valor_nota_credito_anulacion'])}, "
            f"{sql_num(row['valor_tarjeta_debito'])}, {sql_num(row['valor_tarjeta_credito'])}, "
            f"{sql_num(row['valor_pago_banco'])}, {sql_num(row['valor_efectivo'])}, {sql_num(row['valor_place'])}, "
            f"{sql_num(row['valor_2x1'])}, {sql_int(row['creditos_orden'])}, {sql_int(row['referencia_liquidacion'])}, "
            f"{sql_int(row['grupo_facturacion_codigo'])}, {sql_str(row['descripcion_grupo_facturacion'])}, "
            f"{sql_str(row['ubicacion_texto'])}, {sql_str(row['formulario_texto'])}, {sql_int(row['numero_formulario'])}, "
            f"{sql_str(row['creado_por_texto'])}, {sql_str(row['actualizado_por_texto'])}, {sql_str(row['sistema_origen'])}"
            ") ON CONFLICT (orden_externa) DO UPDATE SET "
            "estudiante_id = EXCLUDED.estudiante_id, periodo_id = EXCLUDED.periodo_id, "
            "diplomado_id = EXCLUDED.diplomado_id, sede_id = EXCLUDED.sede_id, "
            "seccional_id = EXCLUDED.seccional_id, modalidad_id = EXCLUDED.modalidad_id, "
            "jornada_id = EXCLUDED.jornada_id, "
            "clasificacion_contable_id = EXCLUDED.clasificacion_contable_id, "
            "estado_pago_academico_id = EXCLUDED.estado_pago_academico_id, "
            "estado_pago_financiero_id = EXCLUDED.estado_pago_financiero_id, "
            "tipo_inscripcion = EXCLUDED.tipo_inscripcion, "
            "fecha_creacion_academica = EXCLUDED.fecha_creacion_academica, "
            "fecha_creacion_financiera = EXCLUDED.fecha_creacion_financiera, "
            "fecha_pago_liquidacion = EXCLUDED.fecha_pago_liquidacion, "
            "fecha_recibo = EXCLUDED.fecha_recibo, "
            "fecha_siguiente_pago = EXCLUDED.fecha_siguiente_pago, "
            "fecha_pago_anterior = EXCLUDED.fecha_pago_anterior, "
            "periodo_ultimo_pago_texto = EXCLUDED.periodo_ultimo_pago_texto, "
            "valor_orden = EXCLUDED.valor_orden, valor_liquidado = EXCLUDED.valor_liquidado, "
            "valor_pagado = EXCLUDED.valor_pagado, valor_pago_directo = EXCLUDED.valor_pago_directo, "
            "saldo_favor = EXCLUDED.saldo_favor, valor_credito = EXCLUDED.valor_credito, "
            "valor_icetex = EXCLUDED.valor_icetex, valor_contratos = EXCLUDED.valor_contratos, "
            "valor_becas_descuentos = EXCLUDED.valor_becas_descuentos, "
            "valor_otras_notas_credito = EXCLUDED.valor_otras_notas_credito, "
            "valor_nota_credito_anulacion = EXCLUDED.valor_nota_credito_anulacion, "
            "valor_tarjeta_debito = EXCLUDED.valor_tarjeta_debito, "
            "valor_tarjeta_credito = EXCLUDED.valor_tarjeta_credito, "
            "valor_pago_banco = EXCLUDED.valor_pago_banco, valor_efectivo = EXCLUDED.valor_efectivo, "
            "valor_place = EXCLUDED.valor_place, valor_2x1 = EXCLUDED.valor_2x1, "
            "creditos_orden = EXCLUDED.creditos_orden, "
            "referencia_liquidacion = EXCLUDED.referencia_liquidacion, "
            "grupo_facturacion_codigo = EXCLUDED.grupo_facturacion_codigo, "
            "descripcion_grupo_facturacion = EXCLUDED.descripcion_grupo_facturacion, "
            "ubicacion_texto = EXCLUDED.ubicacion_texto, formulario_texto = EXCLUDED.formulario_texto, "
            "numero_formulario = EXCLUDED.numero_formulario, "
            "creado_por_texto = EXCLUDED.creado_por_texto, "
            "actualizado_por_texto = EXCLUDED.actualizado_por_texto, "
            "sistema_origen = EXCLUDED.sistema_origen, "
            "updated_at = now();"
        )
    lines.append("")
    lines.append("COMMIT;")
    lines.append("")

    OUT_HECHOS.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_CAT} bytes={OUT_CAT.stat().st_size}")
    print(f"wrote {OUT_HECHOS} bytes={OUT_HECHOS.stat().st_size} lineas={len(lines)}")


if __name__ == "__main__":
    generar()
