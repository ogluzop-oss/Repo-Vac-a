"""
Migración 0335 — Métrica del objetivo de Productividad (€ / visitas). ADITIVA, idempotente,
reversible.

Petición explícita: unificar "Objetivos" del CRM (que admitía objetivos de Nº de visitas, además
de ventas/oportunidades) dentro de "Productividad" de Ventas (que solo admitía un importe fijo en
€), para no tener dos pantallas de objetivos redundantes. `metrica` distingue si `valor` es un
importe (€, comportamiento de SIEMPRE, por eso el default preserva cada fila existente tal cual) o
un conteo de visitas — ortogonal a `tipo_objetivo` (centro/empleado): un mismo centro puede tener
un objetivo de facturación Y uno de visitas vigentes a la vez, versionados por separado.
"""

VERSION = "0335"
DESCRIPCION = "Métrica del objetivo de productividad (€ / visitas)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute(
        "ALTER TABLE productividad_objetivos "
        "ADD COLUMN IF NOT EXISTS metrica ENUM('eur','visitas') NOT NULL DEFAULT 'eur'")


def revertir(cur):
    cur.execute("ALTER TABLE productividad_objetivos DROP COLUMN IF EXISTS metrica")
