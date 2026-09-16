"""Normaliza el Excel de Diplomados (Órdenes Financieras de Educación Continuada)
al modelo diplomas.

El Excel trae 3 hojas, pero solo una es fuente real:
  - "26e - Reporte de Ordenes Financ" (420 filas, 82 columnas) -> hecho orden_financiera
  - "Asesores" y "Diplomados " son tablas dinámicas de Excel (resúmenes PAGO/NO PAGO ya
    calculados), NO son fuente y se ignoran.

MODO ACUMULAR (piloto de automatización, sep 2026): a diferencia de la primera versión,
este normalizador ya NO le asigna un id numérico propio a cada catálogo/estudiante — en
su lugar, cada fila de los CSV usa directamente su llave natural (código de diplomado,
documento del estudiante, etc.). generar_sql_carga.py arma con eso un UPSERT
(INSERT ... ON CONFLICT ... DO UPDATE) que deja que Postgres resuelva los ids reales,
así funciona igual de bien en la primera carga que acumulando sobre datos ya existentes.

ADVERTENCIAS CON NIVEL (regla acordada con Sara/Angie para la automatización): cada fila
de advertencias_calidad.csv trae un nivel "critico" o "info".
  - "critico": un dato no tiene el tipo que le corresponde (fecha inválida, documento/
    monto no numérico) o falta un campo requerido para identificar la fila. La fila se
    omite de la carga. Un proceso automático debe DETENERSE antes de tocar CORE si hay
    alguna advertencia "critico" en la corrida.
  - "info": formato irregular pero el dato sí tiene el tipo correcto (ej. teléfono con
    10 dígitos... pero mal formateado) o inconsistencias de negocio ya conocidas (ej. la
    fila sin diplomado). No bloquea la carga, solo queda anotado para revisar después.

No depende de columnas ni catálogos de tickets/Zarigüeya ni de Jurídico/legal_consulting.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook

DEFAULT_EXCEL = Path(
    r"C:\Users\angie_vera\Downloads\26e05 Diplomados  - Reporte de Ordenes Financieras "
    r"registradas y pagadas por Periodo Academico.xlsx"
)
OUT_DIR = Path(__file__).resolve().parent

SHEET_ORDENES = "26e - Reporte de Ordenes Financ"

EMPTY = {"", "-", "N/A", "NONE"}

# Confirmado con el dueño del dato (no inferido): mapeo informativo de Tip_identificacion,
# documentado aquí y en 01_diplomas_schema.sql. El valor crudo es el que se guarda en
# estudiante_ref.tipo_documento_origen; este mapeo es solo referencia.
TIPO_DOCUMENTO_NOTA = {
    "C": "Cédula de Ciudadanía",
    "PPT": "Permiso de Protección Temporal",
    "E": "Cédula de Extranjería",
    "T": "Tarjeta de Identidad",
}

REQUIRED = [
    "Orden", "Doc_alum", "Periodo", "Est_pag_aca", "Est_pag_financiero",
    "Fondo", "Nombre_fondo", "Producto", "Fuente", "Valor_orden",
]

FORMULARIO_RE = re.compile(r"Formulario:(\d+)")


# ---------------------------------------------------------------------------
# Helpers de limpieza (mismo patrón que pipeline_juridico/normalizar_juridico.py)
# ---------------------------------------------------------------------------

def fold(value: object) -> str:
    text = "" if value is None else str(value).strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).upper()


def is_empty(value: object) -> bool:
    if value is None:
        return True
    return fold(value) in EMPTY


def norm_header(value: object) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def clean_text(value: object) -> str | None:
    if is_empty(value):
        return None
    return re.sub(r"\s+", " ", str(value).strip())


def clean_int(value: object) -> int | None:
    """Puede lanzar ValueError si value trae texto no numérico (a propósito: eso lo debe
    capturar quien llama y tratarlo como advertencia crítica, no dejar que reviente)."""
    if is_empty(value):
        return None
    return int(str(value).strip())


def clean_money(value: object) -> str | None:
    """Convierte '.00', '1100659.00', '-508316.20' (o int/float) a texto decimal '%.2f'.
    Puede lanzar ValueError si value no es un número válido (mismo criterio que clean_int)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    text = str(value).strip()
    if text == "" or text == ".":
        return None
    return f"{float(text):.2f}"


def clean_date(value: object) -> str | None:
    """No lanza excepción: si value no es una fecha real de Excel, se trata como dato
    crítico por el llamador (comparando is_empty vs el resultado), no aquí."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return None


def clean_date_estricto(value: object, campo: str) -> str | None:
    """Como clean_date, pero si value trae ALGO que no es fecha real de Excel (ej. texto
    escrito a mano), lanza ValueError -- para que la fila se marque crítica en vez de
    guardar silenciosamente NULL en una fecha que sí traía un dato (solo inválido)."""
    if is_empty(value):
        return None
    if isinstance(value, (datetime, date)):
        return clean_date(value)
    raise ValueError(f"{campo}={value!r} no es una fecha válida de Excel")


def clean_phone(value: object) -> str | None:
    if is_empty(value):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Lectura + validación de hoja
# ---------------------------------------------------------------------------

def find_header_row(raw: list[tuple], required: list[str], sheet_name: str) -> tuple[int, dict[str, int]]:
    required_norm = {norm_header(r) for r in required}
    for i, row in enumerate(raw[:5]):
        headers = {norm_header(c): j for j, c in enumerate(row) if c is not None}
        if required_norm <= set(headers.keys()):
            return i, headers
    raise ValueError(
        f"No encuentro los encabezados esperados en la hoja {sheet_name!r}: {required}"
    )


def normalizar(excel: Path, out_dir: Path | None = None) -> dict[str, int]:
    dest = out_dir or OUT_DIR
    dest.mkdir(parents=True, exist_ok=True)
    wb = load_workbook(excel, data_only=True, read_only=True)

    sheet_names = {norm_header(n): n for n in wb.sheetnames}
    if norm_header(SHEET_ORDENES) not in sheet_names:
        wb.close()
        raise ValueError(
            f"El Excel debe tener la hoja {SHEET_ORDENES!r}. Encontradas: {wb.sheetnames}"
        )

    ws = wb[sheet_names[norm_header(SHEET_ORDENES)]]
    raw = list(ws.iter_rows(values_only=True))
    wb.close()

    h_idx, colmap = find_header_row(raw, REQUIRED, SHEET_ORDENES)
    data = [r for r in raw[h_idx + 1:] if any(c is not None for c in r)]

    def c(row: tuple, name: str) -> object:
        idx = colmap.get(norm_header(name))
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    # -- catálogos: solo se guarda la llave natural + su(s) atributo(s) descriptivo(s),
    #    sin id propio (Postgres lo asigna vía UPSERT, ver generar_sql_carga.py) ----------
    periodos: "OrderedDict[str, None]" = OrderedDict()
    diplomados: "OrderedDict[str, str]" = OrderedDict()          # codigo -> nombre
    sedes: "OrderedDict[int, str]" = OrderedDict()                # codigo -> nombre
    seccionales: "OrderedDict[int, str]" = OrderedDict()          # codigo -> nombre
    modalidades: "OrderedDict[int, str]" = OrderedDict()          # codigo -> nombre
    jornadas: "OrderedDict[int, str]" = OrderedDict()             # codigo -> nombre
    estados_pago: "OrderedDict[str, None]" = OrderedDict()
    clasif_contable: "OrderedDict[tuple, None]" = OrderedDict()   # (fondo_codigo, fondo_nombre, producto, fuente)

    estudiantes: dict[str, list[object]] = {}   # documento_origen -> fila de atributos (primera vez que aparece)

    ordenes: list[list[object]] = []
    advertencias: list[list[object]] = []

    orden_externa_vistas: set[int] = set()

    for i, row in enumerate(data, start=h_idx + 2):  # +2: 1-based y salta header
        fila_ref = f"{SHEET_ORDENES}!fila{i}"

        faltantes = [campo for campo in REQUIRED if is_empty(c(row, campo))]
        if faltantes:
            advertencias.append([fila_ref, ",".join(faltantes), "", "campo requerido vacío; fila omitida de orden_financiera", "critico"])
            continue

        # A partir de aquí, cualquier campo numérico/fecha que no se pueda interpretar con
        # su tipo esperado (ValueError de clean_int/clean_money/clean_date_estricto) se
        # trata como CRÍTICO: la fila se omite completa, en vez de dejar que el error
        # tumbe todo el proceso o se cuele un dato mal tipado. Esta es la regla que
        # definieron Sara/Angie para bloquear la carga automática.
        try:
            orden_externa = clean_int(c(row, "Orden"))
            if orden_externa in orden_externa_vistas:
                advertencias.append([fila_ref, "Orden", orden_externa, "Orden duplicada en el Excel; fila omitida (se conserva la primera)", "critico"])
                continue

            # -- estudiante_ref (dimensión: 1 fila por documento) --------------
            documento = str(clean_int(c(row, "Doc_alum")))
            if documento not in estudiantes:
                nombres = clean_text(c(row, "Nom_tercero"))
                seg_nombre = clean_text(c(row, "Seg_nombre"))
                apellido1 = clean_text(c(row, "Pri_apellido"))
                apellido2 = clean_text(c(row, "Seg_apellido"))
                nombre_completo = fold(" ".join(p for p in (nombres, seg_nombre, apellido1, apellido2) if p))

                tel_casa = clean_phone(c(row, "Tel_casa"))
                tel_cel = clean_phone(c(row, "Tel_celular"))
                for campo, val in (("Tel_casa", tel_casa), ("Tel_celular", tel_cel)):
                    if val is not None and len(val) != 10:
                        advertencias.append([fila_ref, campo, val, "longitud de teléfono inusual (se guarda tal cual, revisar a mano)", "info"])

                estudiantes[documento] = [
                    documento,
                    clean_text(c(row, "Tip_identificacion")),
                    clean_int(c(row, "Id_tercero")),
                    nombres,
                    seg_nombre,
                    apellido1,
                    apellido2,
                    nombre_completo,
                    clean_text(c(row, "Gen_tercero")),
                    clean_date(c(row, "Fec_nac")),
                    clean_date(c(row, "Fec_exp")),
                    clean_text(c(row, "Email")),
                    clean_text(c(row, "Email_per")),
                    tel_casa,
                    tel_cel,
                    clean_text(c(row, "Direccion_casa")),
                ]

            # -- catálogos de la orden (se registran solo para la carga de catálogos;
            #    en orden_financiera.csv se referencian por su código, no por un id) ----
            periodo_raw = clean_text(c(row, "Periodo"))
            periodos[periodo_raw] = None

            cod_uni = clean_text(c(row, "Cod_uni"))
            if cod_uni is not None:
                diplomados.setdefault(cod_uni, clean_text(c(row, "Nom_unidad")) or cod_uni)
            else:
                advertencias.append([
                    fila_ref, "Cod_uni/Nom_unidad/Cod_sede/Cod_secc/Cod_moda/Id_jornada", "",
                    "fila sin datos de diplomado/sede/seccional/modalidad/jornada en el Excel de origen; "
                    "Nomcencos y Grupo_facturacion de esta fila se contradicen sobre cuál sería el diplomado; "
                    "se carga la orden con esos campos en NULL, sin adivinar el valor",
                    "info",
                ])

            cod_sede = clean_int(c(row, "Cod_sede"))
            if cod_sede is not None:
                sedes.setdefault(cod_sede, clean_text(c(row, "Sede")) or str(cod_sede))

            cod_secc = clean_int(c(row, "Cod_secc"))
            if cod_secc is not None:
                seccionales.setdefault(cod_secc, clean_text(c(row, "Seccional")) or str(cod_secc))

            cod_moda = clean_int(c(row, "Cod_moda"))
            if cod_moda is not None:
                modalidades.setdefault(cod_moda, clean_text(c(row, "Modalidad")) or str(cod_moda))

            id_jornada = clean_int(c(row, "Id_jornada"))
            if id_jornada is not None:
                jornadas.setdefault(id_jornada, clean_text(c(row, "Nom_jornada")) or str(id_jornada))

            fondo_codigo = clean_int(c(row, "Fondo"))
            fondo_nombre = clean_text(c(row, "Nombre_fondo"))
            producto = clean_text(c(row, "Producto"))
            fuente = clean_text(c(row, "Fuente"))
            clasif_contable[(fondo_codigo, fondo_nombre, producto, fuente)] = None

            estado_aca_nombre = fold(c(row, "Est_pag_aca"))
            estado_fin_nombre = fold(c(row, "Est_pag_financiero"))
            estados_pago[estado_aca_nombre] = None
            estados_pago[estado_fin_nombre] = None

            formulario_texto = clean_text(c(row, "Formulario"))
            numero_formulario = None
            if formulario_texto:
                m = FORMULARIO_RE.match(formulario_texto)
                if m:
                    numero_formulario = int(m.group(1))

            fila_orden = [
                orden_externa, documento, periodo_raw, cod_uni, cod_sede, cod_secc, cod_moda, id_jornada,
                fondo_codigo, producto, fuente, estado_aca_nombre, estado_fin_nombre,
                clean_text(c(row, "Nuevo")),
                clean_date(c(row, "Fec_cre_acad")),
                clean_date_estricto(c(row, "Fec_finan"), "Fec_finan"),
                clean_date(c(row, "Fec_pago_liq")),
                clean_date(c(row, "Fec_recibo")),
                clean_date_estricto(c(row, "Fec_siguiente"), "Fec_siguiente"),
                clean_date(c(row, "Fec_anterior")),
                clean_text(c(row, "Periodo_ult_pago")),
                clean_money(c(row, "Valor_orden")),
                clean_money(c(row, "Val_liquidado")),
                clean_money(c(row, "Val_pagado")),
                clean_money(c(row, "Val_pago_directo")),
                clean_money(c(row, "Saldo_favor")),
                clean_money(c(row, "Val_credito")),
                clean_money(c(row, "Val_icetex")),
                clean_money(c(row, "Val_contratos")),
                clean_money(c(row, "Val_becdtos")),
                clean_money(c(row, "Val_otras_ncr")),
                clean_money(c(row, "Ncr_anulacion")),
                clean_money(c(row, "Val_tarjeta_debito")),
                clean_money(c(row, "Val_tarjeta_credito")),
                clean_money(c(row, "Val_pago_banco")),
                clean_money(c(row, "Val_efectivo")),
                clean_money(c(row, "Val_place")),
                clean_money(c(row, "Val_2x1")),
                clean_int(c(row, "Creditos_orden")),
                clean_int(c(row, "Ref_liquidacion")),
                clean_int(c(row, "Grupo_facturacion")),
                clean_text(c(row, "Descripcion_grupo")),
                clean_text(c(row, "Ubicacion")),
                formulario_texto,
                numero_formulario,
                clean_text(c(row, "Usu_crea")),
                clean_text(c(row, "Usu_actu")),
                clean_text(c(row, "Documento")),
            ]
        except (ValueError, TypeError) as exc:
            advertencias.append([
                fila_ref, "(varios)", str(exc),
                "un valor numérico o de fecha no se pudo interpretar con el tipo esperado; fila omitida sin cargar",
                "critico",
            ])
            continue

        orden_externa_vistas.add(orden_externa)
        ordenes.append(fila_orden)

    # -- volcado a CSV / xlsx (sin columna "id": la llave natural va en cada fila) ------
    periodo_rows = [[k] for k in periodos.keys()]
    diplomado_rows = [[k, v] for k, v in diplomados.items()]
    sede_rows = [[k, v] for k, v in sedes.items()]
    seccional_rows = [[k, v] for k, v in seccionales.items()]
    modalidad_rows = [[k, v] for k, v in modalidades.items()]
    jornada_rows = [[k, v] for k, v in jornadas.items()]
    estado_pago_rows = [[k] for k in estados_pago.keys()]
    clasif_rows = [[k[0], k[1], k[2], k[3]] for k in clasif_contable.keys()]
    estudiante_rows = list(estudiantes.values())

    tables = {
        "periodo_academico": (["codigo"], periodo_rows),
        "diplomado": (["codigo", "nombre"], diplomado_rows),
        "sede": (["codigo", "nombre"], sede_rows),
        "seccional": (["codigo", "nombre"], seccional_rows),
        "modalidad": (["codigo", "nombre"], modalidad_rows),
        "jornada": (["codigo", "nombre"], jornada_rows),
        "estado_pago": (["nombre"], estado_pago_rows),
        "clasificacion_contable": (
            ["fondo_codigo", "fondo_nombre", "producto", "fuente"],
            clasif_rows,
        ),
        "estudiante_ref": (
            ["documento_origen", "tipo_documento_origen", "id_tercero_origen", "nombres",
             "segundo_nombre", "apellido1", "apellido2", "nombre_completo_normalizado", "genero",
             "fecha_nacimiento", "fecha_expedicion_documento", "email_institucional", "email_personal",
             "telefono_casa", "telefono_celular", "direccion"],
            estudiante_rows,
        ),
        "orden_financiera": (
            ["orden_externa", "estudiante_documento", "periodo_codigo", "diplomado_codigo",
             "sede_codigo", "seccional_codigo", "modalidad_codigo", "jornada_codigo",
             "clasif_fondo_codigo", "clasif_producto", "clasif_fuente",
             "estado_pago_academico_nombre", "estado_pago_financiero_nombre",
             "tipo_inscripcion", "fecha_creacion_academica", "fecha_creacion_financiera",
             "fecha_pago_liquidacion", "fecha_recibo", "fecha_siguiente_pago",
             "fecha_pago_anterior", "periodo_ultimo_pago_texto", "valor_orden", "valor_liquidado",
             "valor_pagado", "valor_pago_directo", "saldo_favor", "valor_credito", "valor_icetex",
             "valor_contratos", "valor_becas_descuentos", "valor_otras_notas_credito",
             "valor_nota_credito_anulacion", "valor_tarjeta_debito", "valor_tarjeta_credito",
             "valor_pago_banco", "valor_efectivo", "valor_place", "valor_2x1", "creditos_orden",
             "referencia_liquidacion", "grupo_facturacion_codigo", "descripcion_grupo_facturacion",
             "ubicacion_texto", "formulario_texto", "numero_formulario", "creado_por_texto",
             "actualizado_por_texto", "sistema_origen"],
            ordenes,
        ),
    }

    out_xlsx = Workbook()
    first = True
    for name, (hdrs, rows) in tables.items():
        write_csv(dest / f"{name}.csv", hdrs, rows)
        sheet = out_xlsx.active if first else out_xlsx.create_sheet(name)
        if first:
            sheet.title = name
            first = False
        sheet.append(hdrs)
        for row in rows:
            sheet.append(list(row))

    n_criticas = sum(1 for a in advertencias if a[-1] == "critico")
    if advertencias:
        write_csv(dest / "advertencias_calidad.csv", ["fila", "campo", "valor", "detalle", "nivel"], advertencias)

    xlsx_path = dest / "diplomados_normalizado.xlsx"
    try:
        out_xlsx.save(xlsx_path)
    except PermissionError:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        xlsx_path = dest / f"diplomados_normalizado_{stamp}.xlsx"
        out_xlsx.save(xlsx_path)
        print(
            "diplomados_normalizado.xlsx está abierto (Excel o Cursor). "
            f"Se guardó copia en {xlsx_path.name}. Cierra el original para la próxima."
        )

    print(f"ordenes={len(ordenes)} estudiantes={len(estudiante_rows)}")
    print(f"periodos={len(periodo_rows)} diplomados={len(diplomado_rows)} sedes={len(sede_rows)}")
    print(f"seccionales={len(seccional_rows)} modalidades={len(modalidad_rows)} jornadas={len(jornada_rows)}")
    print(f"estados_pago={len(estado_pago_rows)} clasificaciones_contables={len(clasif_rows)}")
    print(f"advertencias={len(advertencias)} (criticas={n_criticas})" + (" -> ver advertencias_calidad.csv" if advertencias else ""))
    print(f"xlsx={xlsx_path}")

    return {
        "ordenes": len(ordenes),
        "estudiantes": len(estudiante_rows),
        "advertencias": len(advertencias),
        "advertencias_criticas": n_criticas,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Normaliza el Excel de Diplomados al modelo diplomas.")
    parser.add_argument(
        "excel",
        nargs="?",
        default=str(DEFAULT_EXCEL),
        help="Ruta del xlsx de Diplomados (default: Descargas/26e05 Diplomados ...xlsx)",
    )
    args = parser.parse_args()
    path = Path(args.excel)
    if not path.exists():
        raise SystemExit(f"No existe el Excel: {path}")
    normalizar(path, OUT_DIR)


if __name__ == "__main__":
    main()
