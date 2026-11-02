"""Consulta básica de artículos (nombre/descripción/precio/categoría) — capa fina para consumidores
que no deben hablar con la BD directamente (p. ej. la REST API). Clon del patrón de `services.stock`/
`services.ubicacion` (buscar por código o nombre, solo lectura).

Deliberadamente DISTINTO de `services.catalogo.service` (el catálogo PIM/e-commerce, `/catalogo/
productos`): ese filtra por visibilidad web y solo expone el código interno del artículo a roles
ADMINISTRADOR/SUPERADMIN — inútil para un OPERARIO de tienda consultando cualquier artículo, publicado
a la web o no. Este servicio no aplica ninguno de esos filtros."""


def buscar(id_empresa, texto: str = "", limite: int = 50) -> list[dict]:
    """Busca artículos por código o nombre. Sin filtrar por `bloqueado`/`estado`/visibilidad web —
    un empleado de tienda debe poder consultar cualquier artículo."""
    from src.db.conexion import _filas_a_dicts, obtener_conexion
    like = f"%{texto}%"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, nombre, descripcion, categoria, seccion, precio, precio_promo, "
                "promo_activa, imagen FROM articulos "
                "WHERE id_empresa=%s AND (codigo LIKE %s OR nombre LIKE %s) "
                "ORDER BY nombre ASC LIMIT %s",
                (id_empresa, like, like, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception:
        return []
