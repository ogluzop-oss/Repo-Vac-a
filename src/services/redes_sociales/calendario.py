"""
Calendario de contenidos — CRUD de publicaciones programadas multiplataforma + publicación real
(dispatch a `plataformas/*.py`). Sin infraestructura de cron en el servidor (auditoría: no existe
en todo el repo), así que el disparo periódico de `procesar_programadas` sigue el MISMO patrón ya
usado por `gui/menu_principal.py` (`_timer_badges`, `QTimer` en el proceso de escritorio) — ver
`gui/redes_sociales_gui.py::_timer_calendario`.
"""

import logging

from src.services.redes_sociales import cuentas as _cuentas
from src.services.redes_sociales.plataformas import cliente_para

logger = logging.getLogger("redes_sociales.calendario")

TIPOS_CONTENIDO = ("imagen", "video", "carrusel", "texto")
ESTADOS = ("borrador", "programada", "publicada", "fallida")


class CalendarioError(Exception):
    pass


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def crear_publicacion(id_cuenta, plataforma, *, titulo=None, contenido=None,
                      tipo_contenido="texto", ruta_adjunto=None, fecha_programada=None,
                      creado_por=None, id_empresa=None) -> dict:
    if tipo_contenido not in TIPOS_CONTENIDO:
        raise CalendarioError(f"Tipo de contenido no válido: {tipo_contenido!r}")
    id_empresa = _emp(id_empresa)
    estado = "programada" if fecha_programada else "borrador"
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO redes_sociales_publicaciones (id_empresa, id_cuenta, plataforma, "
                "titulo, contenido, tipo_contenido, ruta_adjunto, estado, fecha_programada, "
                "creado_por) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_cuenta, plataforma, titulo, contenido, tipo_contenido,
                 ruta_adjunto, estado, fecha_programada, creado_por))
            id_pub = cur.lastrowid
        return {"ok": True, "id": id_pub}
    except Exception as e:
        logger.error("crear_publicacion: %s", e)
        raise CalendarioError("No se pudo crear la publicación.") from e


def actualizar_publicacion(id_publicacion, *, id_empresa=None, **campos) -> dict:
    permitidos = {"titulo", "contenido", "tipo_contenido", "ruta_adjunto", "fecha_programada",
                 "estado"}
    sets, params = [], []
    for k, v in campos.items():
        if k in permitidos:
            sets.append(f"{k}=%s"); params.append(v)
    if not sets:
        return {"ok": False, "error": "sin_cambios"}
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE redes_sociales_publicaciones SET {', '.join(sets)} "
                       f"WHERE id=%s AND id_empresa=%s", (*params, id_publicacion, id_empresa))
            ok = cur.rowcount > 0
        return {"ok": ok}
    except Exception as e:
        logger.error("actualizar_publicacion(%s): %s", id_publicacion, e)
        return {"ok": False, "error": "error_interno"}


def eliminar_publicacion(id_publicacion, id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM redes_sociales_publicaciones WHERE id=%s AND "
                       "id_empresa=%s AND estado != 'publicada'", (id_publicacion, id_empresa))
            ok = cur.rowcount > 0
        return {"ok": ok}
    except Exception as e:
        logger.error("eliminar_publicacion(%s): %s", id_publicacion, e)
        return {"ok": False, "error": "error_interno"}


def listar_publicaciones(*, estado=None, desde=None, hasta=None, id_empresa=None,
                         limite=500) -> list:
    id_empresa = _emp(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if estado:
        filtros.append("estado=%s"); params.append(estado)
    if desde:
        filtros.append("fecha_programada >= %s"); params.append(desde)
    if hasta:
        filtros.append("fecha_programada <= %s"); params.append(hasta)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM redes_sociales_publicaciones WHERE " + " AND ".join(filtros) +
                " ORDER BY fecha_programada ASC, id DESC LIMIT %s", (*params, int(limite)))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_publicaciones: %s", e)
        return []


def _publicar_dispatch(pub, cuenta, id_empresa):
    cli = cliente_para(pub["plataforma"])
    if cli is None:
        return {"ok": False, "estado": "plataforma_no_soportada"}
    if pub["plataforma"] in ("instagram", "facebook"):
        canal = "instagram" if pub["plataforma"] == "instagram" else "facebook"
        return cli.publicar(pub["id_cuenta"], cuenta["id_externo"], texto=pub.get("contenido"),
                            url_imagen=pub.get("ruta_adjunto"), canal=canal, id_empresa=id_empresa)
    if pub["plataforma"] == "tiktok":
        if not pub.get("ruta_adjunto"):
            return {"ok": False, "estado": "falta_ruta_adjunto"}
        return cli.publicar(pub["id_cuenta"], ruta_video_url=pub["ruta_adjunto"],
                            titulo=pub.get("titulo"), id_empresa=id_empresa)
    if pub["plataforma"] == "x":
        return cli.publicar(pub["id_cuenta"], pub.get("contenido") or "", id_empresa=id_empresa)
    if pub["plataforma"] == "youtube":
        return cli.publicar(id_empresa=id_empresa)
    return {"ok": False, "estado": "plataforma_no_soportada"}


def publicar_ahora(id_publicacion, id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    pubs = listar_publicaciones(id_empresa=id_empresa, limite=100000)
    pub = next((p for p in pubs if p["id"] == id_publicacion), None)
    if not pub:
        raise CalendarioError("Publicación no encontrada.")
    cuentas_todas = _cuentas.listar(id_empresa=id_empresa)
    cuenta = next((c for c in cuentas_todas if c["id"] == pub["id_cuenta"]), None)
    if not cuenta:
        raise CalendarioError("La cuenta conectada de esta publicación ya no existe.")

    r = _publicar_dispatch(pub, cuenta, id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            if r.get("ok"):
                cur.execute(
                    "UPDATE redes_sociales_publicaciones SET estado='publicada', "
                    "fecha_publicada=NOW(), externo_id=%s, error_publicacion=NULL WHERE id=%s",
                    (r.get("id_externo"), id_publicacion))
            else:
                motivo = r.get("estado") or "error"
                cur.execute(
                    "UPDATE redes_sociales_publicaciones SET estado='fallida', "
                    "error_publicacion=%s WHERE id=%s", (motivo[:255], id_publicacion))
    except Exception as e:
        logger.error("publicar_ahora: persistencia %s: %s", id_publicacion, e)
    return r


def procesar_programadas(id_empresa=None) -> dict:
    """Busca publicaciones `programada` con `fecha_programada` ya vencida y las publica. Llamado
    periódicamente por el `QTimer` de la GUI (ver docstring del módulo)."""
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM redes_sociales_publicaciones WHERE id_empresa=%s AND "
                "estado='programada' AND fecha_programada <= NOW() LIMIT 50", (id_empresa,))
            ids = [r[0] for r in cur.fetchall()]
    except Exception as e:
        logger.error("procesar_programadas: %s", e)
        return {"ok": False, "error": "error_interno"}

    publicadas = fallidas = 0
    for id_pub in ids:
        try:
            r = publicar_ahora(id_pub, id_empresa=id_empresa)
            if r.get("ok"):
                publicadas += 1
            else:
                fallidas += 1
        except Exception as e:
            logger.error("procesar_programadas: publicación %s: %s", id_pub, e)
            fallidas += 1
    return {"ok": True, "publicadas": publicadas, "fallidas": fallidas}
