-- Modelo de Educación Continuada / Diplomados (Excel "26e05 Diplomados - Reporte de
-- Ordenes Financieras registradas y pagadas por Periodo Academico").
-- Esquema diplomas: crear vacío en la instancia CORE antes de correr este script,
-- misma base "core" de GCP donde vive legal_consulting. Este script es IDEMPOTENTE
-- (CREATE ... IF NOT EXISTS) y solo agrega objetos dentro de diplomas.
-- No toca core, academic_workload, tickets, legal_consulting ni ningún otro esquema.
--
-- Igual que en tickets/legal_consulting: 0 FK físicas cross-schema. El cruce con
-- core.person se resuelve por aplicación, vía estudiante_ref.core_person_id + match_status
-- (a diferencia de Jurídico, aquí SÍ hay documento de estudiante en el Excel, así que el
-- match primario es por documento, con nombre normalizado como respaldo).
--
-- Fuente Excel: 1 sola hoja real de datos ("26e - Reporte de Ordenes Financ", 420 filas,
-- 82 columnas). Las hojas "Asesores" y "Diplomados " son tablas dinámicas ya calculadas
-- por Excel (resúmenes PAGO/NO PAGO) — no son fuente, se ignoran.

CREATE SCHEMA IF NOT EXISTS diplomas;

-- ---------------------------------------------------------------------------
-- Catálogos (viven en el Excel, no en CORE)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS diplomas.periodo_academico (
    id              smallserial PRIMARY KEY,
    codigo          varchar(20) NOT NULL UNIQUE      -- valor crudo de "Periodo" (ej. '2600000')
);

CREATE TABLE IF NOT EXISTS diplomas.diplomado (
    id              smallserial PRIMARY KEY,
    codigo          varchar(10) NOT NULL UNIQUE,      -- Cod_uni (ej. CE510)
    nombre          varchar(200) NOT NULL             -- Nom_unidad (nombre canónico)
);

CREATE TABLE IF NOT EXISTS diplomas.sede (
    id              smallserial PRIMARY KEY,
    codigo          integer NOT NULL UNIQUE,          -- Cod_sede
    nombre          varchar(100) NOT NULL             -- Sede
);

CREATE TABLE IF NOT EXISTS diplomas.seccional (
    id              smallserial PRIMARY KEY,
    codigo          integer NOT NULL UNIQUE,          -- Cod_secc
    nombre          varchar(100) NOT NULL             -- Seccional
);

CREATE TABLE IF NOT EXISTS diplomas.modalidad (
    id              smallserial PRIMARY KEY,
    codigo          integer NOT NULL UNIQUE,          -- Cod_moda
    nombre          varchar(60) NOT NULL              -- Modalidad
);

CREATE TABLE IF NOT EXISTS diplomas.jornada (
    id              smallserial PRIMARY KEY,
    codigo          integer NOT NULL UNIQUE,          -- Id_jornada
    nombre          varchar(60) NOT NULL              -- Nom_jornada
);

CREATE TABLE IF NOT EXISTS diplomas.estado_pago (
    id              smallserial PRIMARY KEY,
    nombre          varchar(20) NOT NULL UNIQUE       -- PAGO, NO PAGO
);

-- Fondo/Producto/Fuente vienen constantes en este lote (1 sola combinación), pero se
-- catalogan igual por si el próximo extracto trae otra sede/producto contable.
CREATE TABLE IF NOT EXISTS diplomas.clasificacion_contable (
    id              smallserial PRIMARY KEY,
    fondo_codigo    integer NOT NULL,                 -- Fondo
    fondo_nombre    varchar(100) NOT NULL,             -- Nombre_fondo
    producto        varchar(120) NOT NULL,             -- Producto
    fuente          varchar(120) NOT NULL,             -- Fuente
    UNIQUE (fondo_codigo, producto, fuente)
);

-- ---------------------------------------------------------------------------
-- Puente lógico a CORE (id CORE copiado si se resuelve, sin FK física)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS diplomas.estudiante_ref (
    id                              serial PRIMARY KEY,
    documento_origen                varchar(20) NOT NULL UNIQUE,   -- Doc_alum
    tipo_documento_origen           varchar(10),                    -- Tip_identificacion: crudo (ver comentario)
    id_tercero_origen               integer,                        -- Id_tercero (ERP origen; trazabilidad, no llave)
    nombres                         varchar(100),                   -- Nom_tercero
    segundo_nombre                  varchar(100),                   -- Seg_nombre
    apellido1                       varchar(100),                   -- Pri_apellido
    apellido2                       varchar(100),                   -- Seg_apellido
    nombre_completo_normalizado     varchar(300) NOT NULL,          -- para match por nombre (fold: mayúsculas, sin tildes)
    genero                          varchar(5),                     -- Gen_tercero
    fecha_nacimiento                date,                            -- Fec_nac
    fecha_expedicion_documento      date,                            -- Fec_exp
    email_institucional             varchar(200),                   -- Email
    email_personal                  varchar(200),                   -- Email_per
    telefono_casa                   varchar(30),                    -- Tel_casa (texto: se preservan anomalías de origen)
    telefono_celular                varchar(30),                    -- Tel_celular
    direccion                       varchar(250),                   -- Direccion_casa
    core_person_id                  integer,                        -- lógico -> core.person.id
    match_status                    varchar(20) NOT NULL DEFAULT 'pendiente'
        CHECK (match_status IN ('documento', 'nombre_normalizado', 'pendiente', 'sin_match')),
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()   -- se actualiza en cada UPSERT (ver 02_cargar_catalogos.sql)
);

-- ALTER en vez de solo CREATE: estas columnas se agregaron después de la primera carga
-- (modo acumular/UPSERT), así que si la tabla ya existía sin ellas, esto las añade sin tocar
-- las filas que ya había.
ALTER TABLE diplomas.estudiante_ref ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE diplomas.estudiante_ref ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

-- ---------------------------------------------------------------------------
-- Hecho
-- ---------------------------------------------------------------------------

-- 1 fila = 1 orden financiera de matrícula a un diplomado ("26e - Reporte de Ordenes Financ").
-- orden_externa (columna "Orden") es única 420/420 en el lote de origen -> PK natural del hecho.
-- diplomado_id/sede_id/seccional_id/modalidad_id/jornada_id son NULLABLE: la orden 728897 llegó
-- del Excel sin esos datos y con Nomcencos/Grupo_facturacion contradictorios entre sí sobre cuál
-- sería el diplomado real; se carga con esos campos en NULL y queda en advertencias_calidad.csv
-- para revisión manual, sin adivinar el valor.
CREATE TABLE IF NOT EXISTS diplomas.orden_financiera (
    id                              serial PRIMARY KEY,
    orden_externa                   bigint NOT NULL UNIQUE,          -- Orden
    estudiante_id                   integer NOT NULL REFERENCES diplomas.estudiante_ref (id),
    periodo_id                      smallint NOT NULL REFERENCES diplomas.periodo_academico (id),
    diplomado_id                    smallint REFERENCES diplomas.diplomado (id),
    sede_id                         smallint REFERENCES diplomas.sede (id),
    seccional_id                    smallint REFERENCES diplomas.seccional (id),
    modalidad_id                    smallint REFERENCES diplomas.modalidad (id),
    jornada_id                      smallint REFERENCES diplomas.jornada (id),
    clasificacion_contable_id       smallint NOT NULL REFERENCES diplomas.clasificacion_contable (id),
    estado_pago_academico_id        smallint NOT NULL REFERENCES diplomas.estado_pago (id),
    estado_pago_financiero_id       smallint NOT NULL REFERENCES diplomas.estado_pago (id),
    tipo_inscripcion                varchar(20),                     -- Nuevo: NUEVO/ANTIGUO
    fecha_creacion_academica        date,                            -- Fec_cre_acad
    fecha_creacion_financiera       date,                            -- Fec_finan
    fecha_pago_liquidacion          date,                            -- Fec_pago_liq
    fecha_recibo                    date,                            -- Fec_recibo
    fecha_siguiente_pago            date,                            -- Fec_siguiente
    fecha_pago_anterior             date,                            -- Fec_anterior
    periodo_ultimo_pago_texto       varchar(20),                     -- Periodo_ult_pago (formato mixto de origen)
    valor_orden                     numeric(14,2) NOT NULL,          -- Valor_orden
    valor_liquidado                 numeric(14,2),                   -- Val_liquidado (NULL si NO PAGO financiero)
    valor_pagado                    numeric(14,2),                   -- Val_pagado (NULL si NO PAGO financiero)
    valor_pago_directo              numeric(14,2),                   -- Val_pago_directo
    saldo_favor                     numeric(14,2),                   -- Saldo_favor
    valor_credito                   numeric(14,2),                   -- Val_credito
    valor_icetex                    numeric(14,2),                   -- Val_icetex
    valor_contratos                 numeric(14,2),                   -- Val_contratos
    valor_becas_descuentos          numeric(14,2),                   -- Val_becdtos
    valor_otras_notas_credito       numeric(14,2),                   -- Val_otras_ncr
    valor_nota_credito_anulacion    numeric(14,2),                   -- Ncr_anulacion
    valor_tarjeta_debito            numeric(14,2),                   -- Val_tarjeta_debito
    valor_tarjeta_credito           numeric(14,2),                   -- Val_tarjeta_credito
    valor_pago_banco                numeric(14,2),                   -- Val_pago_banco
    valor_efectivo                  numeric(14,2),                   -- Val_efectivo
    valor_place                     numeric(14,2),                   -- Val_place
    valor_2x1                       numeric(14,2),                   -- Val_2x1
    creditos_orden                  smallint,                        -- Creditos_orden
    referencia_liquidacion          bigint,                          -- Ref_liquidacion
    grupo_facturacion_codigo        integer,                         -- Grupo_facturacion (informativo; NO es 1:1 con diplomado, ver comentario)
    descripcion_grupo_facturacion   varchar(200),                    -- Descripcion_grupo
    ubicacion_texto                 varchar(200),                    -- Ubicacion (ciudad del estudiante, texto libre de origen)
    formulario_texto                text,                            -- Formulario (crudo, pipe-delimited de origen)
    numero_formulario               integer,                         -- parseado de "Formulario:<n>|...", si viene
    creado_por_texto                varchar(200),                    -- Usu_crea
    actualizado_por_texto           varchar(200),                    -- Usu_actu
    sistema_origen                  varchar(20),                     -- Documento (constante 'FECO' en este lote; nomenclatura del sistema origen)
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()   -- se actualiza en cada UPSERT (ver 02_cargar_catalogos.sql)
);

ALTER TABLE diplomas.orden_financiera ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

-- ---------------------------------------------------------------------------
-- Seguimiento de archivos de Drive (piloto de automatización, sep 2026)
-- ---------------------------------------------------------------------------

-- 1 fila = 1 archivo de Drive que el robot ya procesó (ver automatizacion/sync_diplomados.py).
-- UNIQUE (drive_file_id, md5_checksum): si el MISMO archivo se re-sube con contenido
-- distinto (md5 distinto), se procesa de nuevo; si es idéntico, se ignora (no se reprocesa).
CREATE TABLE IF NOT EXISTS diplomas.archivo_procesado (
    id                      serial PRIMARY KEY,
    drive_file_id           varchar(100) NOT NULL,
    nombre_archivo          varchar(300) NOT NULL,
    md5_checksum            varchar(64),
    procesado_en            timestamptz NOT NULL DEFAULT now(),
    ordenes_en_archivo      integer,
    advertencias_totales    integer,
    advertencias_criticas   integer,
    estado                  varchar(20) NOT NULL
        CHECK (estado IN ('cargado', 'bloqueado_criticas', 'error')),
    detalle                 text,
    UNIQUE (drive_file_id, md5_checksum)
);

CREATE INDEX IF NOT EXISTS ix_orden_estudiante   ON diplomas.orden_financiera (estudiante_id);
CREATE INDEX IF NOT EXISTS ix_orden_diplomado    ON diplomas.orden_financiera (diplomado_id);
CREATE INDEX IF NOT EXISTS ix_orden_periodo      ON diplomas.orden_financiera (periodo_id);
CREATE INDEX IF NOT EXISTS ix_orden_estado_fin   ON diplomas.orden_financiera (estado_pago_financiero_id);
CREATE INDEX IF NOT EXISTS ix_orden_fecha_fin    ON diplomas.orden_financiera (fecha_creacion_financiera);

COMMENT ON SCHEMA diplomas IS
    'Órdenes financieras de matrícula a diplomados (educación continuada). Maestro de estudiante se resuelve contra CORE por documento (respaldo: nombre normalizado), sin FK física.';
COMMENT ON COLUMN diplomas.estudiante_ref.core_person_id IS
    'Join lógico: primero core.person.document = documento_origen; si no hay match, core.person.full_name normalizado = nombre_completo_normalizado. Sin FK. Ver 04a_verificar_match_core_person.sql.';
COMMENT ON COLUMN diplomas.estudiante_ref.tipo_documento_origen IS
    'Código crudo de "Tip_identificacion": C=Cédula de Ciudadanía, PPT=Permiso de Protección Temporal, E=Cédula de Extranjería, T=Tarjeta de Identidad (confirmado con el dueño del dato, no inferido). Comparar contra core.person.type_document al hacer el match.';
COMMENT ON COLUMN diplomas.orden_financiera.diplomado_id IS
    'NULL en la orden 728897 (única en el lote de origen): el Excel no trae Cod_uni/Nom_unidad/sede/seccional/modalidad/jornada para esa fila, y las columnas de respaldo (Nomcencos vs Grupo_facturacion) se contradicen sobre cuál sería. No se adivinó; ver advertencias_calidad.csv.';
COMMENT ON COLUMN diplomas.orden_financiera.grupo_facturacion_codigo IS
    'Código de grupo de facturación del ERP origen. NO es una clasificación estable de diplomado: el mismo código aparece con distintos diplomados en distintas filas del lote (ej. grupo 2 = GESTIÓN DE PROYECTOS y EXCEL Y POWER BI). Se guarda como dato informativo/trazabilidad, sin catálogo ni integridad referencial.';
COMMENT ON COLUMN diplomas.orden_financiera.sistema_origen IS
    'Valor crudo de la columna "Documento" del Excel. Constante ''FECO'' en las 420 filas de este lote (nomenclatura fija del sistema origen, confirmado con el dueño del dato). Se guarda tal cual por si varía en un próximo extracto.';
