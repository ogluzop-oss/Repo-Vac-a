"""
Accesores canónicos de `articulos`. Tras la PK compuesta (id_empresa, codigo) — migr 0181 — estas lecturas/
escrituras filtran por EMPRESA. Retrocompatibles (Strangler): `id_empresa` es opcional y por defecto se toma de
la sesión (`empresa_actual_id`), de modo que las llamadas existentes quedan correctamente aisladas por tenant
sin cambiarlas. En instalaciones de una sola empresa el comportamiento es idéntico.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id() or EMPRESA_DEFAULT_ID
    except Exception:
        return EMPRESA_DEFAULT_ID


# ============================================================
# BLOQUE CONSULTA DE ARTÍCULOS
# ============================================================

def obtener_articulos(id_empresa=None):
    id_empresa = _emp(id_empresa)
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT codigo, nombre, Stock_total, precio, capacidad_lineal, bloqueado, "
            "ultima_recepcion, siguiente_recepcion, ubicacion_tienda FROM articulos WHERE id_empresa=%s",
            (id_empresa,)
        )
        return cursor.fetchall()


# ============================================================
# BLOQUE ACTUALIZACIÓN DE ARTÍCULOS
# ============================================================

def actualizar_precio(codigo, nuevo_precio, id_empresa=None):
    id_empresa = _emp(id_empresa)
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE articulos SET precio=%s WHERE codigo=%s AND id_empresa=%s",
            (nuevo_precio, codigo, id_empresa)
        )
        conn.commit()
    return True


def actualizar_emoji(codigo, emoji, id_empresa=None):
    """Actualiza el emoji representativo del artículo (presentacional, para el TPV táctil)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE articulos SET emoji=%s WHERE codigo=%s AND id_empresa=%s",
                           (emoji or None, codigo, id_empresa))
            conn.commit()
        return True
    except Exception:
        return False


# ============================================================
# FÍSICA DE SEGURIDAD DEL AUTOCOBRO (Capa 1)
# peso_unitario (kg) + tolerancia_peso (kg): master data que alimenta el control antifraude.
# ============================================================

def obtener_fisica_seguridad(codigo, id_empresa=None):
    """Devuelve {'peso_unitario': float|None, 'tolerancia_peso': float|None} del artículo (o None)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            cur = conn.cursor()
            cur.execute("SELECT peso_unitario, tolerancia_peso FROM articulos WHERE codigo=%s AND id_empresa=%s",
                        (codigo, id_empresa))
            row = cur.fetchone()
            if not row:
                return None
            pu = float(row[0]) if row[0] is not None else None
            tp = float(row[1]) if row[1] is not None else None
            return {"peso_unitario": pu, "tolerancia_peso": tp}
    except Exception:
        return None


def guardar_fisica_seguridad(codigo, peso_unitario=None, tolerancia_peso=None, id_empresa=None):
    """Actualiza el peso esperado y la tolerancia del artículo (kg). Valores None/<=0 → NULL (usa
    los valores por defecto del motor). Devuelve (ok, mensaje)."""
    id_empresa = _emp(id_empresa)

    def _norm(v):
        try:
            v = float(str(v).replace(",", "."))   # tolera coma decimal
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None
    pu, tp = _norm(peso_unitario), _norm(tolerancia_peso)
    try:
        with obtener_conexion() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM articulos WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
            if not cur.fetchone():
                return False, "Artículo no encontrado."
            cur.execute(
                "UPDATE articulos SET peso_unitario=%s, tolerancia_peso=%s WHERE codigo=%s AND id_empresa=%s",
                (pu, tp, codigo, id_empresa))
            conn.commit()
        return True, "Física de seguridad actualizada."
    except Exception as e:
        return False, f"Error al guardar: {e}"
