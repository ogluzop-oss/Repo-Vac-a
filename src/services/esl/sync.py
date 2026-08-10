"""
Sincronización de precios a las etiquetas — PUSH MANUAL.

El sistema NO empuja solo al cambiar el precio: calcula qué etiquetas están PENDIENTES (su precio efectivo
actual difiere del último sincronizado, o nunca se sincronizaron / dieron error) y el usuario dispara el
push con `sincronizar()`. El precio efectivo respeta la promoción activa del artículo (mismo criterio que la
ficha de artículo). Idempotente y multiempresa/tienda.
"""

import datetime as _dt
import logging

from src.db.conexion import obtener_conexion
from src.services.esl import config, registro
from src.services.esl.config import _ctx

logger = logging.getLogger("esl.sync")


def precio_efectivo(codigo, id_empresa=None):
    """Precio que debe mostrar la etiqueta: precio de promoción si hay promo activa, si no el P.V.P."""
    from src.db.conexion import obtener_articulo
    art = obtener_articulo(codigo, id_empresa=id_empresa)   # tenant-aware: propaga la empresa
    if not art:
        return None
    try:
        if art.get("promo_activa") and art.get("precio_promo") not in (None, ""):
            return round(float(art["precio_promo"]), 4)
        return round(float(art.get("precio") or 0), 4)
    except (TypeError, ValueError):
        return None


def _pendiente(lab, pe):
    if lab.get("estado") != "ACTUALIZADA":
        return True
    ps = lab.get("precio_sincronizado")
    if ps is None:
        return True
    try:
        return pe is not None and abs(float(ps) - pe) > 0.0001
    except (TypeError, ValueError):
        return True


def pendientes(id_empresa=None, id_tienda=None):
    """Etiquetas que necesitan sincronizarse. Añade `precio_actual` (precio efectivo a empujar)."""
    e, t = _ctx(id_empresa, id_tienda)
    out = []
    for lab in registro.listar(id_empresa=e, id_tienda=t):
        pe = precio_efectivo(lab["codigo_articulo"], e)
        if _pendiente(lab, pe):
            out.append({**lab, "precio_actual": pe})
    return out


def _marcar(id_label, estado, precio_sinc, error):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE esl_labels SET estado=%s, precio_sincronizado=%s, ultimo_error=%s, ultima_sync=%s "
                "WHERE id=%s",
                (estado, precio_sinc, error, _dt.datetime.now(), id_label))
    except Exception as ex:
        logger.error("_marcar: %s", ex)


def sincronizar(codigos=None, id_empresa=None, id_tienda=None):
    """PUSH MANUAL. Empuja las etiquetas pendientes (opcionalmente solo las de `codigos`, iterable de
    códigos de artículo). Devuelve {'total','ok','error'}."""
    e, t = _ctx(id_empresa, id_tienda)
    gw = config.gateway(e, t)
    filtro = set(codigos) if codigos else None
    total = okc = errc = 0
    for lab in pendientes(id_empresa=e, id_tienda=t):
        if filtro is not None and lab["codigo_articulo"] not in filtro:
            continue
        total += 1
        pe = lab.get("precio_actual")
        datos = {"codigo": lab["codigo_articulo"], "precio": pe, "plantilla": lab.get("plantilla")}
        res = gw.push(lab["label_id"], datos)
        if res.get("ok"):
            okc += 1
            _marcar(lab["id"], "ACTUALIZADA", pe, None)
        else:
            errc += 1
            _marcar(lab["id"], "ERROR", None, (res.get("detalle") or "")[:255])
    return {"total": total, "ok": okc, "error": errc}


def localizar(label_id, id_empresa=None, id_tienda=None):
    """Hace parpadear una etiqueta para localizarla en el lineal (a través del gateway configurado)."""
    e, t = _ctx(id_empresa, id_tienda)
    return config.gateway(e, t).localizar(str(label_id))
