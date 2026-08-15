"""
Migración 0193 — Unificación de `id_tienda` (INT) · grupo ESL: `esl_config` y `esl_labels`. Idempotente,
reversible.

Continúa la unificación iniciada en 0192. Las tablas ESL están **claveadas de forma exacta** por
(empresa, tienda): cada configuración/etiqueta pertenece a UNA tienda concreta; no existe el concepto de
"todas las tiendas". Por eso, a diferencia de `precio_reglas`, aquí el valor sin contexto/central se mapea a
**0** (tienda por defecto/central), nunca a NULL. Código no numérico ('ALMC') → 0; numérico → su int.

`services/esl/config._ctx` (usado por config/registro/sync) se actualiza en el mismo PR para coaccionar la
tienda a entero con `tienda_actual_id_int`.
"""

VERSION = "0193"
DESCRIPCION = "Unificar id_tienda a INT (grupo ESL: esl_config, esl_labels): '' /código -> 0, numérico -> int"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = ("esl_config", "esl_labels")


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
                    "WHEN id_tienda IS NULL OR id_tienda='' THEN '0' "
                    "WHEN id_tienda REGEXP '^[0-9]+$' THEN id_tienda "
                    "ELSE '0' END")
        cur.execute(f"ALTER TABLE {t} MODIFY id_tienda INT NULL DEFAULT 0")


def revertir(cur):
    for t in _TABLAS:
        if _tipo_columna(cur, t, "id_tienda") != "int":
            continue
        cur.execute(f"ALTER TABLE {t} MODIFY id_tienda VARCHAR(36) NULL DEFAULT NULL")
