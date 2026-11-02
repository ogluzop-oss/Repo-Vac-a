"""
Imagen Y ETIQUETA (ambas editables por el superadministrador) de cada una de las 9 familias a
granel.

Las familias son código fijo (`services.tpv.familias_granel`, no filas de BD), así que necesitan
su propia tabla pequeña (`familias_granel_imagenes`, migraciones 0306/0307) para guardar qué
imagen y qué texto eligió el superadmin para cada una — mismo patrón de "ruta en BD, bytes en
documentos/" que `productos_granel.imagen`/`articulos.imagen`, sin inventar un mecanismo nuevo.
`etiqueta_personalizada` NULL = se sigue mostrando la etiqueta por defecto del código.
"""

import logging

logger = logging.getLogger("tpv.familias_granel_imagenes")


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def obtener(codigo_familia: str) -> dict | None:
    """{ruta_imagen, etiqueta_personalizada} de una familia, o None si no tiene nada guardado."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT ruta_imagen, etiqueta_personalizada FROM familias_granel_imagenes "
                "WHERE codigo_familia=%s", (codigo_familia,))
            r = cur.fetchone()
            if not r:
                return None
            if isinstance(r, dict):
                return {"ruta_imagen": r.get("ruta_imagen"),
                       "etiqueta_personalizada": r.get("etiqueta_personalizada")}
            return {"ruta_imagen": r[0], "etiqueta_personalizada": r[1]}
    except Exception as e:
        logger.error("obtener(%s): %s", codigo_familia, e)
        return None


def listar_mapa() -> dict:
    """{codigo_familia: {ruta_imagen, etiqueta_personalizada}} de TODAS las familias con algo
    guardado — una sola consulta para pintar las 9 tarjetas de golpe."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo_familia, ruta_imagen, etiqueta_personalizada "
                       "FROM familias_granel_imagenes")
            filas = cur.fetchall()
            out = {}
            for f in filas:
                if isinstance(f, dict):
                    cod, ruta, etq = f.get("codigo_familia"), f.get("ruta_imagen"), f.get("etiqueta_personalizada")
                else:
                    cod, ruta, etq = f[0], f[1], f[2]
                out[cod] = {"ruta_imagen": ruta, "etiqueta_personalizada": etq}
            return out
    except Exception as e:
        logger.error("listar_mapa: %s", e)
        return {}


def guardar(codigo_familia: str, *, ruta_imagen: str | None = None,
           etiqueta: str | None = None) -> bool:
    """Guarda la imagen y/o la etiqueta de una familia. Los parámetros no indicados (None)
    conservan el valor ya guardado (no lo borran) — permite editar solo el texto o solo la
    imagen desde el mismo formulario sin pisar el otro campo."""
    actual = obtener(codigo_familia) or {}
    ruta_final = ruta_imagen if ruta_imagen is not None else actual.get("ruta_imagen")
    etq_final = etiqueta if etiqueta is not None else actual.get("etiqueta_personalizada")
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO familias_granel_imagenes (codigo_familia, ruta_imagen, etiqueta_personalizada) "
                "VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE ruta_imagen=VALUES(ruta_imagen), "
                "etiqueta_personalizada=VALUES(etiqueta_personalizada)",
                (codigo_familia, ruta_final, etq_final))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar(%s): %s", codigo_familia, e)
        return False
