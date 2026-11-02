"""
Migración 0291 — Fase 4 e-commerce (Catálogo Web / Canal Web): tema visual del storefront.
ADITIVA, reversible, idempotente.

`web_config` (tabla YA existente, una fila por empresa — NO se crea ninguna tabla nueva): se le
añade `tema_json` (JSON, como string, de las secciones/bloques del editor visual —
`gui/tema_editor_dialog.py` / `backend/storefront_bloques.py`). NULL/vacío = sin tema guardado
todavía: el storefront (`backend/storefront.py::pagina_home`) sigue generando el layout fijo de
siempre — cero regresión para las tiendas que ya existen.
"""

VERSION = "0291"
DESCRIPCION = "Tema visual del storefront (web_config.tema_json)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
        "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    n = r[0] if not isinstance(r, dict) else list(r.values())[0]
    return int(n) > 0


def aplicar(cur):
    if not _existe_columna(cur, "web_config", "tema_json"):
        cur.execute("ALTER TABLE web_config ADD COLUMN tema_json MEDIUMTEXT DEFAULT NULL")


def revertir(cur):
    if _existe_columna(cur, "web_config", "tema_json"):
        cur.execute("ALTER TABLE web_config DROP COLUMN tema_json")
