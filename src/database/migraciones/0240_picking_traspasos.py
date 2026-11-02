"""
Migración 0240 — Picking de traspasos logísticos (`documentos_logisticos_lineas.picking_completo`).

Ajuste post-lanzamiento · Módulo 8 (Logística): el flujo de traspasos no tenía ningún paso de picking
— un documento nacía directo en `EN TRANSITO`. Esta columna marca, por línea, si el artículo ya se ha
recogido físicamente antes de expedir el traspaso (granularidad por línea/palé, a petición del
usuario). 0/NULL = no recogida. ADITIVA, idempotente, reversible.
"""

VERSION = "0240"
DESCRIPCION = "Columna documentos_logisticos_lineas.picking_completo (picking de traspasos)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("SHOW COLUMNS FROM documentos_logisticos_lineas LIKE 'picking_completo'")
    if not cur.fetchone():
        cur.execute(
            "ALTER TABLE documentos_logisticos_lineas "
            "ADD COLUMN picking_completo TINYINT(1) NOT NULL DEFAULT 0"
        )


def revertir(cur):
    cur.execute("SHOW COLUMNS FROM documentos_logisticos_lineas LIKE 'picking_completo'")
    if cur.fetchone():
        cur.execute("ALTER TABLE documentos_logisticos_lineas DROP COLUMN picking_completo")
