"""
Bulk Products Service — Smart Manager AI TPV Enterprise
Manages productos_granel table: CRUD, price validation, category listing.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("tpv.bulk")


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def _rows_to_dicts(cur):
    """Tuple-cursor → list[dict] using column names from cur.description."""
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]


def _row_to_dict(cur, row):
    if not row:
        return None
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row, strict=False))


# ─── Read ─────────────────────────────────────────────────────────────────────

def listar_productos_activos() -> list[dict]:
    """Return all active bulk products ordered by category then name."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, nombre, precio_kg, emoji, categoria, codigo_interno
                    FROM productos_granel
                    WHERE activo = 1
                    ORDER BY categoria, nombre
                """)
                return _rows_to_dicts(cur)
    except Exception as e:
        logger.error(f"listar_productos_activos: {e}")
        return []


def listar_todos() -> list[dict]:
    """Return all bulk products (including inactive) for admin management."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, nombre, precio_kg, emoji, categoria,
                           codigo_interno, activo, ultima_actualizacion
                    FROM productos_granel
                    ORDER BY categoria, nombre
                """)
                return _rows_to_dicts(cur)
    except Exception as e:
        logger.error(f"listar_todos: {e}")
        return []


def obtener_por_id(pid: int) -> dict | None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, nombre, precio_kg, emoji, categoria, codigo_interno, activo "
                    "FROM productos_granel WHERE id = %s", (pid,)
                )
                row = cur.fetchone()
                return _row_to_dict(cur, row)
    except Exception as e:
        logger.error(f"obtener_por_id: {e}")
        return None


# ─── Write ────────────────────────────────────────────────────────────────────

def guardar_producto(nombre: str, precio_kg: float, emoji: str = "🛒",
                     categoria: str = "GENERAL", codigo_interno: str = "",
                     pid: int | None = None) -> tuple[bool, str]:
    """Create or update a bulk product. Returns (ok, message)."""
    if not nombre or not nombre.strip():
        return False, "El nombre no puede estar vacío."
    if precio_kg < 0:
        return False, "El precio por kilo no puede ser negativo."
    if precio_kg > 9999:
        return False, "El precio por kilo parece incorrecto (>9999 €)."

    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                if pid:
                    cur.execute("""
                        UPDATE productos_granel
                        SET nombre=%s, precio_kg=%s, emoji=%s, categoria=%s, codigo_interno=%s
                        WHERE id=%s
                    """, (nombre.strip(), round(precio_kg, 3), emoji, categoria.upper(),
                          codigo_interno or None, pid))
                    msg = f"Producto '{nombre}' actualizado."
                else:
                    cur.execute("""
                        INSERT INTO productos_granel (nombre, precio_kg, emoji, categoria, codigo_interno)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (nombre.strip(), round(precio_kg, 3), emoji, categoria.upper(),
                          codigo_interno or None))
                    msg = f"Producto '{nombre}' creado."
            conn.commit()
        return True, msg
    except Exception as e:
        logger.error(f"guardar_producto: {e}")
        return False, f"Error al guardar: {e}"


def cambiar_estado(pid: int, activo: bool) -> bool:
    """Activate or deactivate a bulk product."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE productos_granel SET activo=%s WHERE id=%s",
                    (1 if activo else 0, pid)
                )
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"cambiar_estado: {e}")
        return False


def actualizar_precio(pid: int, nuevo_precio: float) -> tuple[bool, str]:
    """Update only the price of a bulk product."""
    if nuevo_precio < 0:
        return False, "El precio no puede ser negativo."
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE productos_granel SET precio_kg=%s WHERE id=%s",
                    (round(nuevo_precio, 3), pid)
                )
            conn.commit()
        return True, "Precio actualizado."
    except Exception as e:
        logger.error(f"actualizar_precio: {e}")
        return False, f"Error: {e}"


# ─── Price calculation ────────────────────────────────────────────────────────

def calcular_total(peso_kg: float, precio_kg: float) -> float:
    """Returns rounded total for a weight-based sale."""
    if peso_kg < 0 or precio_kg < 0:
        return 0.0
    return round(peso_kg * precio_kg, 2)


def validar_peso(peso_kg: float) -> tuple[bool, str]:
    """Basic weight sanity check."""
    if peso_kg <= 0:
        return False, "El peso debe ser mayor que cero."
    if peso_kg > 100:
        return False, "Peso inusualmente alto (> 100 kg). Comprueba la báscula."
    return True, ""
