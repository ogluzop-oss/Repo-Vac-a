"""
Migración 0154 — Báscula: familias canónicas + subfamilia. ADITIVA, idempotente, reversible (columna).

Clasifica `productos_granel` en 9 familias canónicas (Dulces, Fruta, Verdura, Carnicería, Pescadería,
Panes, Bollería, Lácteos, Frutos secos) y añade la columna `subfamilia` (apartados de Panes/Bollería).
Reasigna las categorías antiguas de texto libre a los códigos canónicos (ver taxonomía en
`src.services.tpv.familias_granel`). No crea motor nuevo: solo normaliza datos y añade una columna.
"""

VERSION = "0154"
DESCRIPCION = "Báscula: familias canónicas + columna subfamilia (Panes/Bollería) y normalización"
REVERSIBLE = True
REQUIERE_BACKUP = False

# Reasignación por categoría antigua → código canónico. FRESCOS era un cajón mixto: por defecto va a
# LACTEOS y el jamón se reasigna explícitamente a CARNICERIA por nombre (más abajo).
_CAT = [
    (["FRUTOS SECOS", "FRUTOS_SECOS"], "FRUTOS_SECOS"),
    (["CARNE", "CARNICERÍA", "CARNICERIA"], "CARNICERIA"),
    (["PESCADO", "PESCADERÍA", "PESCADERIA"], "PESCADERIA"),
    (["PAN", "PANES"], "PANES"),
    (["BOLLERÍA", "BOLLERIA"], "BOLLERIA"),
    (["QUESOS", "LÁCTEOS", "LACTEOS", "FRESCOS"], "LACTEOS"),
    (["FRUTA"], "FRUTA"),
    (["VERDURA"], "VERDURA"),
    (["DULCES"], "DULCES"),
]

_CANONICAS = ("DULCES", "FRUTA", "VERDURA", "CARNICERIA", "PESCADERIA",
              "PANES", "BOLLERIA", "LACTEOS", "FRUTOS_SECOS", "OTROS")


def aplicar(cur):
    # 1) Columna subfamilia (apartados de Panes/Bollería). Idempotente.
    try:
        cur.execute("ALTER TABLE productos_granel "
                    "ADD COLUMN IF NOT EXISTS subfamilia VARCHAR(100) DEFAULT NULL")
    except Exception:
        pass  # tabla puede no existir en instalaciones mínimas
    # 2) Normalización de categorías antiguas → códigos canónicos de familia.
    try:
        for antiguas, canonica in _CAT:
            marcadores = ",".join(["%s"] * len(antiguas))
            cur.execute(f"UPDATE productos_granel SET categoria=%s "
                        f"WHERE UPPER(categoria) IN ({marcadores})",
                        (canonica, *[a.upper() for a in antiguas]))
        # Jamón (curado) del antiguo cajón FRESCOS → CARNICERIA.
        cur.execute("UPDATE productos_granel SET categoria='CARNICERIA' "
                    "WHERE nombre LIKE '%Jamón%' OR nombre LIKE '%Jamon%'")
        # Cualquier categoría no canónica (GENERAL, vacía, desconocida) → OTROS (no se pierde nada).
        marcadores = ",".join(["%s"] * len(_CANONICAS))
        cur.execute(f"UPDATE productos_granel SET categoria='OTROS' "
                    f"WHERE categoria IS NULL OR UPPER(categoria) NOT IN ({marcadores})",
                    tuple(_CANONICAS))
    except Exception:
        pass


def revertir(cur):
    # Estructural: se elimina la columna añadida. La normalización de `categoria` es un saneamiento
    # de datos canónico y NO se revierte (no había un valor "anterior" único fiable).
    try:
        cur.execute("ALTER TABLE productos_granel DROP COLUMN IF EXISTS subfamilia")
    except Exception:
        pass
