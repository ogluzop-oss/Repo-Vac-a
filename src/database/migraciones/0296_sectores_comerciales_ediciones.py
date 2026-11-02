"""
Migración 0296 — Siembra los 5 "Sector Comercial" de `sectores_comerciales` (Smart Suppliers,
migr. 0217) con las mismas 5 ediciones/verticales del software (`services.verticales.VERTICALES`:
Supermarket/Retail/Pharmacy/Textil/Bakery). ADITIVA, reversible, idempotente.

Antes de esta migración, `sectores_comerciales` existía pero NUNCA se sembraba — ninguna empresa
podía tener `empresas.sector_id` asignado (ninguna fila que elegir), lo que bloqueaba
permanentemente la entrada al Portal B2B (`b2b_sesion_empresa.crear_sesion` exige sector asignado).
Pedido explícito: la pestaña "Datos de empresa" de Configuración deja elegir el sector mediante un
desplegable con estas 5 opciones — se siembran aquí para que existan filas que referenciar.
"""

VERSION = "0296"
DESCRIPCION = "Siembra sectores_comerciales con las 5 ediciones (Supermarket/Retail/Pharmacy/Textil/Bakery)"
REVERSIBLE = True
REQUIERE_BACKUP = False

# (codigo, nombre) — codigo en minúsculas (mismo criterio que `services.compras.sectores.crear`).
_SECTORES = (
    ("supermarket", "Supermarket"),
    ("retail", "Retail"),
    ("pharmacy", "Pharmacy"),
    ("textil", "Textil"),
    ("bakery", "Bakery & Coffee"),
)


def aplicar(cur):
    for codigo, nombre in _SECTORES:
        cur.execute("INSERT IGNORE INTO sectores_comerciales (codigo, nombre, activo) VALUES (%s,%s,1)",
                    (codigo, nombre))


def revertir(cur):
    for codigo, _nombre in _SECTORES:
        cur.execute("DELETE FROM sectores_comerciales WHERE codigo=%s", (codigo,))
