"""
Migración 0194 — Unificación de `id_tienda` (INT) · grupo Autocobro: `autocobro_incidencias` y
`autocobro_seguridad_log`. Idempotente, reversible.

Continúa la unificación (0192 precio_reglas, 0193 ESL). Estas tablas son LOGS por tienda usados también
para analítica agregada: una tienda concreta (int; central 'ALMC' → 0) o SIN tienda (NULL) = "todas"
(la analítica no filtra por tienda). Por eso el mapeo es como en precio_reglas: '' → NULL, código → 0,
numérico → int.
"""

VERSION = "0194"
DESCRIPCION = "Unificar id_tienda a INT (grupo Autocobro): '' -> NULL, código -> 0, numérico -> int"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = ("autocobro_incidencias", "autocobro_seguridad_log")


def _tipo_columna(cur, tabla, col):
    cur.execute("SELECT DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None


def aplicar(cur):
    for t in _TABLAS:
        if _tipo_columna(cur, t, "id_tienda") == "int":
            continue
        cur.execute(f"UPDATE {t} SET id_tienda = CASE "
                    "WHEN id_tienda='' THEN NULL "
                    "WHEN id_tienda REGEXP '^[0-9]+$' THEN id_tienda "
                    "ELSE '0' END")
        cur.execute(f"ALTER TABLE {t} MODIFY id_tienda INT NULL DEFAULT NULL")


def revertir(cur):
    for t in _TABLAS:
        if _tipo_columna(cur, t, "id_tienda") != "int":
            continue
        cur.execute(f"ALTER TABLE {t} MODIFY id_tienda VARCHAR(64) NULL DEFAULT NULL")
