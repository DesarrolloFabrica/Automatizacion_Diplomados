# Diccionario de datos — Excel Diplomados

Fuente tipica: reporte `26e05 Diplomados - Reporte de Ordenes Financieras...xlsx`

## Hojas del libro

| Hoja | Uso |
|------|-----|
| `26e - Reporte de Ordenes Financ` | **UNICA fuente** del pipeline (1 fila = 1 orden) |
| Resúmenes (Asesores, Diplomados, Ventas…) | Se **ignoran** (tablas dinámicas / otros reportes) |

El robot exige el nombre exacto de la hoja de órdenes. Si falta, falla con:
`El Excel debe tener la hoja '26e - Reporte de Ordenes Financ'. Encontradas: [...]`

## Columnas requeridas (validación)

Definidas en `normalizar_diplomados.py` → `REQUIRED`:

| Columna Excel | Significado |
|---------------|-------------|
| `Orden` | Número de orden financiera (llave del hecho) |
| `Doc_alum` | Documento del estudiante (cruce fuerte con `core.person`) |
| `Periodo` | Periodo académico |
| `Est_pag_aca` | Estado de pago académico |
| `Est_pag_financiero` | Estado de pago financiero |
| `Fondo` | Código de fondo |
| `Nombre_fondo` | Nombre del fondo |
| `Producto` | Producto / diplomado (código o referencia de producto) |
| `Fuente` | Fuente de financiación |
| `Valor_orden` | Valor de la orden |

## Otras columnas usadas (no todas son REQUIRED)

El Excel trae muchas columnas (~80). El normalizador también toma campos de identificación y contacto del estudiante, sede, modalidad, fechas, etc., cuando existen. Lo que no trae el Excel **no se inventa**.

### Identificación estudiante (referencia)

| Valor `Tip_identificacion` | Significado |
|----------------------------|-------------|
| `C` | Cédula de Ciudadanía |
| `PPT` | Permiso de Protección Temporal |
| `E` | Cédula de Extranjería |
| `T` | Tarjeta de Identidad |

## Destino en base (`esquema diplomas`)

| Concepto | Tabla / uso |
|----------|-------------|
| Catálogos | periodo, diplomado, sede, seccional, modalidad, jornada, estado_pago, clasificacion_contable |
| Puente a CORE | `estudiante_ref` |
| Hecho | `orden_financiera` |
| Control robot | `archivo_procesado` |

## Relación con el error del correo semanal

Si el archivo trae hojas como `Diplomados 26e05` / `Ventas por Asesor` **sin** `26e - Reporte de Ordenes Financ`, el diccionario anterior **no aplica**: es otro formato o un archivo mal subido. Confirmar con quien genera el Excel antes de cambiar el robot.
