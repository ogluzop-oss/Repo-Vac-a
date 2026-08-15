"""
Migración 0196 — Unificación de `id_tienda` (INT) · grupo TPV: `cierres_z` y `tpv_tickets_aparcados`.
Idempotente, reversible. CIERRA la unificación (10/10 tablas).

Matiz por tabla:
- `cierres_z`: el cierre Z pertenece SIEMPRE a una tienda y `id_tienda` forma parte de la CLAVE de
  numeración/hash por tienda (comparaciones exactas `=`) → INT NOT NULL DEFAULT 0 (sin tienda o central
  'ALMC' → 0, nunca NULL). Esta tabla tenía datos reales ('ALMC' → 0).
- `tpv_tickets_aparcados`: ticket aparcado por tienda, consultado con `<=>` (null-safe) → INT NULL
  ('' → NULL; código → 0; numérico → int).
"""

VERSION = "0196"
DESCRIPCION = "Unificar id_tienda a INT (grupo TPV: cierres_z NOT NULL/0, tpv_tickets_aparcados NULL)"
REVERSIBLE = True
REQUIERE_BACKUP = False

# tabla -> (nullable?, ancho varchar original)
_TABLAS = {
    "cierres_z": (False, 64),
    "tpv_tickets_aparcados": (True, 40),
}


def _tipo_columna(cur, tabla, col):
    cur.execute("SELECT DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None


def aplicar(cur):
    for t, (nullable, _ancho) in _TABLAS.items():
        if _tipo_columna(cur, t, "id_tienda") == "int":
            continue
        cur.execute(f"ALTER TABLE {t} MODIFY id_tienda VARCHAR(64) NULL DEFAULT NULL")
        if nullable:
            cur.execute(f"UPDATE {t} SET id_tienda = CASE "
                        "WHEN id_tienda='' THEN NULL "
                        "WHEN id_tienda REGEXP '^[0-9]+$' THEN id_tienda ELSE '0' END")
            cur.execute(f"ALTER TABLE {t} MODIFY id_tienda INT NULL DEFAULT NULL")
        else:
            cur.execute(f"UPDATE {t} SET id_tienda = CASE "
                        "WHEN id_tienda IS NULL OR id_tienda='' THEN '0' "
                        "WHEN id_tienda REGEXP '^[0-9]+$' THEN id_tienda ELSE '0' END")
            cur.execute(f"ALTER TABLE {t} MODIFY id_tienda INT NOT NULL DEFAULT 0")


def revertir(cur):
    for t, (nullable, ancho) in _TABLAS.items():
        if _tipo_columna(cur, t, "id_tienda") != "int":
            continue
        if nullable:
            cur.execute(f"ALTER TABLE {t} MODIFY id_tienda VARCHAR({ancho}) NULL DEFAULT NULL")
        else:
            cur.execute(f"ALTER TABLE {t} MODIFY id_tienda VARCHAR({ancho}) NOT NULL DEFAULT ''")
