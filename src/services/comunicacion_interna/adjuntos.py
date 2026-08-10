"""
Adjuntos unificados de la comunicación interna (circulares y encuestas).

Guarda archivos de texto/imagen tanto del envío en primera instancia (origen EMISOR) como de las
respuestas (origen RESPUESTA, ligados a la confirmación/respuesta). Las imágenes se marcan como
`clase='imagen'` para mostrarse en línea sin abrirlas. Copia el fichero bajo
`documentos/comunicacion_interna/<entidad>/<id>/` con un nombre único y registra la fila en `com_adjuntos`.
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid

logger = logging.getLogger("comunicacion_interna.adjuntos")

_EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def clase_por_extension(nombre: str) -> str:
    """'imagen' si la extensión es de imagen; si no, 'texto'."""
    ext = os.path.splitext(nombre or "")[1].lower()
    return "imagen" if ext in _EXT_IMAGEN else "texto"


def _dir_destino(tipo_entidad: str, id_entidad) -> str:
    try:
        from src.utils import recursos
        ruta = recursos.ruta_salida("documentos", "comunicacion_interna",
                                    str(tipo_entidad).lower(), str(id_entidad))
    except Exception:
        ruta = os.path.join("documentos", "comunicacion_interna",
                            str(tipo_entidad).lower(), str(id_entidad))
    os.makedirs(ruta, exist_ok=True)
    return ruta


def guardar_archivo(origen_path: str, *, tipo_entidad: str, id_entidad, origen: str = "EMISOR",
                    id_respuesta=None, cur=None) -> dict | None:
    """Copia el fichero y registra el adjunto. Devuelve {id, clase, nombre, ruta} o None.
    Si se pasa `cur`, se reutiliza (sin commit propio); si no, abre y hace commit."""
    if not origen_path or not os.path.exists(origen_path):
        return None
    nombre = os.path.basename(origen_path)
    clase = clase_por_extension(nombre)
    destino_dir = _dir_destino(tipo_entidad, id_entidad)
    ext = os.path.splitext(nombre)[1]
    destino = os.path.join(destino_dir, f"{uuid.uuid4().hex}{ext}")
    try:
        shutil.copy2(origen_path, destino)
    except Exception as e:
        logger.error(f"guardar_archivo copia: {e}")
        return None

    def _insert(c):
        c.execute(
            "INSERT INTO com_adjuntos (tipo_entidad, id_entidad, origen, id_respuesta, clase, nombre, ruta) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (tipo_entidad, id_entidad, origen, id_respuesta, clase, nombre, destino))
        return c.lastrowid

    try:
        if cur is not None:
            aid = _insert(cur)
        else:
            with _conn() as conn, conn.cursor() as c:
                aid = _insert(c)
                conn.commit()
        return {"id": aid, "clase": clase, "nombre": nombre, "ruta": destino}
    except Exception as e:
        logger.error(f"guardar_archivo insert: {e}")
        return None


def guardar_varios(rutas, *, tipo_entidad, id_entidad, origen="EMISOR", id_respuesta=None, cur=None):
    """Guarda una lista de rutas de archivo. Devuelve la lista de adjuntos creados."""
    salida = []
    for r in (rutas or []):
        adj = guardar_archivo(r, tipo_entidad=tipo_entidad, id_entidad=id_entidad,
                              origen=origen, id_respuesta=id_respuesta, cur=cur)
        if adj:
            salida.append(adj)
    return salida


def listar_adjuntos(tipo_entidad: str, id_entidad, *, origen=None, id_respuesta="__all__") -> list[dict]:
    """Lista los adjuntos de una entidad. Filtra por origen y/o por id_respuesta si se indican."""
    cond = ["tipo_entidad=%s", "id_entidad=%s"]
    params: list = [tipo_entidad, id_entidad]
    if origen is not None:
        cond.append("origen=%s"); params.append(origen)
    if id_respuesta != "__all__":
        if id_respuesta is None:
            cond.append("id_respuesta IS NULL")
        else:
            cond.append("id_respuesta=%s"); params.append(id_respuesta)
    try:
        with _conn() as conn, conn.cursor() as c:
            c.execute(
                "SELECT id, origen, id_respuesta, clase, nombre, ruta FROM com_adjuntos "
                "WHERE " + " AND ".join(cond) + " ORDER BY id ASC", tuple(params))
            cols = [d[0] for d in c.description]
            return [dict(zip(cols, r)) for r in c.fetchall()]
    except Exception as e:
        logger.debug(f"listar_adjuntos degradado: {e}")
        return []
