"""
Migración 0170 — Conversión CRM → Factura. ADITIVA e IDEMPOTENTE.

Añade `crm_oportunidades.id_factura` (factura generada a partir de la oportunidad). Sirve de enlace
oportunidad↔factura y garantiza la idempotencia de la conversión (no se factura dos veces la misma
oportunidad). No modifica datos existentes.
"""

VERSION = "0170"
DESCRIPCION = "CRM→Factura: columna crm_oportunidades.id_factura"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE crm_oportunidades ADD COLUMN IF NOT EXISTS id_factura INT DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE crm_oportunidades DROP COLUMN IF EXISTS id_factura")
