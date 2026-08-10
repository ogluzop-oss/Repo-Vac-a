"""
Migración 0173 — Conversión CRM → Proyecto. ADITIVA e IDEMPOTENTE.

Añade `crm_oportunidades.id_proyecto` (proyecto generado a partir de la oportunidad). Enlace + idempotencia
(no crea dos proyectos para la misma oportunidad). No modifica datos existentes.
"""

VERSION = "0173"
DESCRIPCION = "CRM→Proyecto: columna crm_oportunidades.id_proyecto"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE crm_oportunidades ADD COLUMN IF NOT EXISTS id_proyecto INT DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE crm_oportunidades DROP COLUMN IF EXISTS id_proyecto")
