"""
Migración 0191 — Columnas de impresión y coordenadas métricas en `ubicaciones`. ADITIVA, idempotente,
reversible.

La pantalla de mapa de tienda (`gui/ubicacion_tienda` → `db/ubicaciones`) usaba tres columnas de
`ubicaciones` que NUNCA existieron en el esquema (ni bootstrap ni migraciones), por lo que las consultas
fallaban en silencio dentro de try/except:

- `impreso`  — marca de etiqueta RFID ya volcada a la cola de impresión (para no reimprimirla).
- `x_metros` / `y_metros` — coordenadas métricas del punto (además de las de píxel `mapa_x`/`mapa_y`).

Con estas columnas, la cola de impresión de etiquetas y el guardado de coordenadas métricas por EPC
vuelven a funcionar. No afecta a stock/ventas; es infraestructura del mapa.
"""

VERSION = "0191"
DESCRIPCION = "ubicaciones: columnas impreso + x_metros/y_metros (cola de etiquetas y coords métricas)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    if not _tiene_columna(cur, "ubicaciones", "impreso"):
        cur.execute("ALTER TABLE ubicaciones ADD COLUMN impreso TINYINT(1) DEFAULT 0")
    if not _tiene_columna(cur, "ubicaciones", "x_metros"):
        cur.execute("ALTER TABLE ubicaciones ADD COLUMN x_metros DOUBLE DEFAULT 0")
    if not _tiene_columna(cur, "ubicaciones", "y_metros"):
        cur.execute("ALTER TABLE ubicaciones ADD COLUMN y_metros DOUBLE DEFAULT 0")


def revertir(cur):
    for col in ("impreso", "x_metros", "y_metros"):
        if _tiene_columna(cur, "ubicaciones", col):
            cur.execute(f"ALTER TABLE ubicaciones DROP COLUMN {col}")
