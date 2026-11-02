"""
Migración 0277 — Libro de Gastos: naturaleza de gasto manual (fijo_mensual / extraordinario).
ADITIVA, reversible, idempotente.

Añade `naturaleza_gasto VARCHAR(20) DEFAULT NULL` a `contab_asientos` para etiquetar DE QUÉ
sección de la pestaña "Libro de Gastos" procede un gasto manual dado de alta vía
`services.contabilidad.posting.registrar_gasto` (origen='gasto'): 'fijo_mensual' (sección
"Gastos fijos mensuales": materiales, alquiler, suministros...) o 'extraordinario' (sección
"Gastos extraordinarios": publicidad y demás gastos puntuales fuera de la operativa habitual).

NULL para TODO asiento ya existente y para cualquier otro origen (compra/venta/nomina/cierre/
plantilla/...) — columna nueva 100% opcional, no reutilizada para nada más, así que no hay
retrocompatibilidad que romper: `asientos.crear_asiento`/`listar_diario` y el resto de llamadores
de `registrar_gasto`/`listar_gastos` (p. ej. la pestaña preexistente "Gastos") siguen exactamente
igual si no pasan el nuevo parámetro opcional. No sustituye a `origen` (que sigue siendo 'gasto'
para TODAS las altas manuales, con o sin naturaleza): es un matiz adicional, solo para poder
filtrar cada sección de la pestaña por sus propias filas sin crear una tabla de gastos paralela.
"""

VERSION = "0277"
DESCRIPCION = "naturaleza_gasto (fijo_mensual/extraordinario) en contab_asientos"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE contab_asientos ADD COLUMN IF NOT EXISTS "
                "naturaleza_gasto VARCHAR(20) DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE contab_asientos DROP COLUMN IF EXISTS naturaleza_gasto")
