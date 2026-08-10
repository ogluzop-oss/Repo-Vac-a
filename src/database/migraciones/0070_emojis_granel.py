"""
Migracion 0070 — Corrige emojis de productos a granel no renderizables. ADITIVA/idempotente.

'Pimiento Rojo' (U+1FAD1) y 'Pistacho' (U+1FAD8) usaban glifos Unicode 13/14 que no se ven
en muchas fuentes de Windows. Se reemplazan por emojis ampliamente soportados. Solo datos.
"""

VERSION = "0070"
DESCRIPCION = "Emojis renderizables para Pimiento Rojo y Pistacho en productos_granel"
REVERSIBLE = False
REQUIERE_BACKUP = False

_FIX = [("Pimiento Rojo", "🌶️"), ("Pistacho", "🥜")]


def aplicar(cur):
    try:
        for nombre, emoji in _FIX:
            cur.execute("UPDATE productos_granel SET emoji=%s WHERE nombre=%s", (emoji, nombre))
    except Exception:
        pass  # tabla puede no existir en instalaciones mínimas


def revertir(cur):
    pass
