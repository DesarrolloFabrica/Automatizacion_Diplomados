-- Solo lectura. No modifica nada. Cruza diplomas.estudiante_ref contra
-- core.person, primero por DOCUMENTO (a diferencia de Jurídico, este Excel sí trae
-- Doc_alum) y, para lo que no matchee por documento, por nombre normalizado como
-- respaldo (mismo mecanismo que pipeline_juridico/04a).
--
-- No asume la extensión unaccent (puede no estar instalada); usa translate() para
-- las tildes/ñ más comunes del español, que sí es función nativa.

-- 1) Match por DOCUMENTO (candidato fuerte: core.person.document = documento_origen)
SELECT
    er.id                 AS estudiante_id,
    er.documento_origen,
    er.tipo_documento_origen,
    er.nombre_completo_normalizado,
    cp.id                 AS core_person_id,
    cp.full_name          AS core_full_name,
    cp.type_document      AS core_type_document,
    cp.document           AS core_document,
    cp.email              AS core_email,
    cp.program_id         AS core_program_id
FROM diplomas.estudiante_ref er
JOIN core.person cp
  ON trim(cp.document) = er.documento_origen
ORDER BY er.id;

-- 2) Estudiantes SIN match por documento (candidatos para el respaldo por nombre)
SELECT er.id, er.documento_origen, er.nombre_completo_normalizado
FROM diplomas.estudiante_ref er
WHERE NOT EXISTS (
    SELECT 1 FROM core.person cp WHERE trim(cp.document) = er.documento_origen
)
ORDER BY er.id;

-- 3) De los que no matchean por documento, respaldo por nombre EXACTO (mayúsculas,
--    sin tildes, espacios colapsados) — igual mecanismo que legal_consulting.
SELECT
    er.id                 AS estudiante_id,
    er.documento_origen,
    er.nombre_completo_normalizado,
    cp.id                 AS core_person_id,
    cp.full_name          AS core_full_name,
    cp.document           AS core_document,
    cp.email              AS core_email
FROM diplomas.estudiante_ref er
JOIN core.person cp
  ON UPPER(regexp_replace(
       translate(trim(cp.full_name), 'áéíóúÁÉÍÓÚñÑüÜ', 'aeiouAEIOUnNuU'),
       '\s+', ' ', 'g'
     )) = er.nombre_completo_normalizado
WHERE NOT EXISTS (
    SELECT 1 FROM core.person cp2 WHERE trim(cp2.document) = er.documento_origen
)
ORDER BY er.id;

-- 4) Estudiantes que no matchean ni por documento ni por nombre exacto (revisar a mano;
--    puede ser que el documento en core.person tenga otro formato, o la persona no esté
--    activa en core en este momento).
SELECT er.id, er.documento_origen, er.tipo_documento_origen, er.nombre_completo_normalizado
FROM diplomas.estudiante_ref er
WHERE NOT EXISTS (
    SELECT 1 FROM core.person cp WHERE trim(cp.document) = er.documento_origen
)
AND NOT EXISTS (
    SELECT 1
    FROM core.person cp
    WHERE UPPER(regexp_replace(
            translate(trim(cp.full_name), 'áéíóúÁÉÍÓÚñÑüÜ', 'aeiouAEIOUnNuU'),
            '\s+', ' ', 'g'
          )) = er.nombre_completo_normalizado
)
ORDER BY er.id;
