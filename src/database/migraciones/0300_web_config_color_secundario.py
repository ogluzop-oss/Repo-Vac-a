"""
Migración 0300 — Generador de Apps Móviles (PWA) · Fase 1: color secundario de marca. ADITIVA,
reversible, idempotente.

`web_config` (fuente única de marca, ver `db/web_tienda.py`) solo tenía UN color (`color`, usado
como acento único tanto en la tienda web como ahora en la app). El manifest.json de una PWA pide
dos colores con roles distintos (`theme_color` = barra del navegador/status-bar del SO,
`background_color` = fondo de la pantalla de carga antes de pintar el primer frame) — reutilizar el
mismo valor para ambos es válido (y es lo que hace `storefront.py` hoy), pero el encargo pide
explícitamente poder fijar un Color Secundario/Acentos propio, así que se añade como columna nueva
en la MISMA tabla (nunca una tabla de tema paralela — `color`/`color_secundario`/`logo_url` ya
conviven en `web_config` junto a `tema_json`)."""

VERSION = "0300"
DESCRIPCION = "Apps móviles (PWA): color_secundario en web_config (acento secundario de marca)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    if not _existe_columna(cur, "web_config", "color_secundario"):
        cur.execute("ALTER TABLE web_config ADD COLUMN color_secundario VARCHAR(9) NULL DEFAULT NULL")


def revertir(cur):
    if _existe_columna(cur, "web_config", "color_secundario"):
        cur.execute("ALTER TABLE web_config DROP COLUMN color_secundario")
