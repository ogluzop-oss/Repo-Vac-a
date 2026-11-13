"""
Migración 0336 — Contenido real (asunto/cuerpo) de las campañas del CRM. ADITIVA, idempotente,
reversible.

Petición explícita: que "Activar" en la pestaña Campañas dispare un envío de correo REAL a los
leads/clientes del segmento, en vez de solo cambiar el estado — para eso la campaña necesita
guardar qué se envía (antes no existía ningún campo de contenido).
"""

VERSION = "0336"
DESCRIPCION = "Asunto/cuerpo del correo de las campañas CRM"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE crm_campanias ADD COLUMN IF NOT EXISTS asunto VARCHAR(255) DEFAULT NULL")
    cur.execute("ALTER TABLE crm_campanias ADD COLUMN IF NOT EXISTS cuerpo TEXT DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE crm_campanias DROP COLUMN IF EXISTS cuerpo")
    cur.execute("ALTER TABLE crm_campanias DROP COLUMN IF EXISTS asunto")
