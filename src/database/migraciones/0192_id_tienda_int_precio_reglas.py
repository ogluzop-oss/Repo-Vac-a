"""
Migración 0192 — Unificación de `id_tienda` (INT) · piloto: tabla `precio_reglas`. ADITIVA en semántica,
idempotente, reversible.

Deuda de esquema: `id_tienda` es INT en 54 tablas y VARCHAR en 10. El modelo canónico es INT
(`tiendas.id`), con la convención de las 41 tablas mayoritarias: **NULL = "todas las tiendas / no
acotado"**, entero positivo = tienda concreta, y el código central 'ALMC' → 0. Los códigos alfanuméricos
en columnas INT provocaban el error 1366 (bug clase-ALMC).

Este piloto convierte `precio_reglas.id_tienda` de VARCHAR(64) NOT NULL DEFAULT '' a INT NULL DEFAULT NULL,
preservando la semántica: '' (aplica a TODAS) → NULL; código no numérico ('ALMC') → 0; numérico → su int.
El código de `services/precio_dinamico/reglas.py` se actualiza en el mismo PR para escribir/leer con esa
convención (NULL = todas).
"""

VERSION = "0192"
DESCRIPCION = "Unificar id_tienda a INT (piloto precio_reglas): '' -> NULL, código -> 0, numérico -> int"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "precio_reglas"


def _tipo_columna(cur, tabla, col):
    cur.execute("SELECT DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    if not r:
        return None
    return (r[0] if not isinstance(r, dict) else list(r.values())[0])


def aplicar(cur):
    if _tipo_columna(cur, _TABLA, "id_tienda") == "int":
        return  # ya migrada
    # 1) relajar NOT NULL para poder normalizar '' -> NULL
    cur.execute(f"ALTER TABLE {_TABLA} MODIFY id_tienda VARCHAR(64) NULL DEFAULT NULL")
    # 2) normalizar valores: '' = todas -> NULL; código no numérico -> 0 (central); numérico -> igual
    cur.execute(f"UPDATE {_TABLA} SET id_tienda = CASE "
                "WHEN id_tienda='' THEN NULL "
                "WHEN id_tienda REGEXP '^[0-9]+$' THEN id_tienda "
                "ELSE '0' END")
    # 3) convertir a INT NULL (convención mayoritaria: NULL = todas)
    cur.execute(f"ALTER TABLE {_TABLA} MODIFY id_tienda INT NULL DEFAULT NULL")


def revertir(cur):
    if _tipo_columna(cur, _TABLA, "id_tienda") != "int":
        return
    cur.execute(f"ALTER TABLE {_TABLA} MODIFY id_tienda VARCHAR(64) NULL DEFAULT NULL")
    cur.execute(f"UPDATE {_TABLA} SET id_tienda='' WHERE id_tienda IS NULL")
    cur.execute(f"ALTER TABLE {_TABLA} MODIFY id_tienda VARCHAR(64) NOT NULL DEFAULT ''")
