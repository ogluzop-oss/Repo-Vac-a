"""
Migración 0246 — Difusión de escaneo remoto por tienda/almacén. ADITIVA, reversible.

Rediseño: una solicitud de escaneo remoto ya NO se dirige al propio teléfono del mismo usuario que
está en escritorio — se difunde a TODOS los móviles logueados en la MISMA tienda/almacén
(`centro_codigo`, el mismo código de centro que ya usa el JWT — ver `src/api/security.py`), nunca a
otras tiendas. El primer dispositivo que la reclama (`reclamada_por`) es el único que puede
completarla; el resto deja de mostrarla en cuanto ve que ya tiene dueño.
"""

VERSION = "0246"
DESCRIPCION = "escaneos_remotos: difusión por centro_codigo + reclamada_por/reclamada_en"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute(
        "ALTER TABLE escaneos_remotos ADD COLUMN IF NOT EXISTS centro_codigo VARCHAR(20) DEFAULT NULL"
    )
    cur.execute(
        "ALTER TABLE escaneos_remotos ADD COLUMN IF NOT EXISTS reclamada_por INT DEFAULT NULL"
    )
    cur.execute(
        "ALTER TABLE escaneos_remotos ADD COLUMN IF NOT EXISTS reclamada_en DATETIME DEFAULT NULL"
    )
    cur.execute(
        "ALTER TABLE escaneos_remotos ADD INDEX IF NOT EXISTS idx_esr_centro "
        "(id_empresa, centro_codigo, estado)"
    )


def revertir(cur):
    cur.execute("ALTER TABLE escaneos_remotos DROP INDEX IF EXISTS idx_esr_centro")
    cur.execute("ALTER TABLE escaneos_remotos DROP COLUMN IF EXISTS reclamada_en")
    cur.execute("ALTER TABLE escaneos_remotos DROP COLUMN IF EXISTS reclamada_por")
    cur.execute("ALTER TABLE escaneos_remotos DROP COLUMN IF EXISTS centro_codigo")
