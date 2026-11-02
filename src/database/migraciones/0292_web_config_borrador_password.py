"""
Migración 0292 — Fase 5 e-commerce (Catálogo Web / Canal Web): borrador con contraseña.
ADITIVA, reversible, idempotente.

`web_config` (tabla YA existente, una fila por empresa — NO se crea ninguna tabla nueva): se le
añaden `borrador` (0 = tienda pública normal, comportamiento IDÉNTICO al de siempre; 1 = la tienda
responde pero exige la contraseña) y `password_hash` (hash Argon2id/SHA-256 vía
`src.seguridad.passwords.hash_password` — NUNCA la contraseña en claro). `activa` sigue siendo la
ÚNICA fuente de "¿la tienda responde o da 404?" (sin cambios); `borrador` es ortogonal y solo
importa si `activa=1`.
"""

VERSION = "0292"
DESCRIPCION = "Borrador con contraseña del storefront (web_config.borrador / password_hash)"
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
    if not _existe_columna(cur, "web_config", "borrador"):
        cur.execute("ALTER TABLE web_config ADD COLUMN borrador TINYINT(1) NOT NULL DEFAULT 0")
    if not _existe_columna(cur, "web_config", "password_hash"):
        cur.execute("ALTER TABLE web_config ADD COLUMN password_hash VARCHAR(255) DEFAULT NULL")


def revertir(cur):
    if _existe_columna(cur, "web_config", "password_hash"):
        cur.execute("ALTER TABLE web_config DROP COLUMN password_hash")
    if _existe_columna(cur, "web_config", "borrador"):
        cur.execute("ALTER TABLE web_config DROP COLUMN borrador")
