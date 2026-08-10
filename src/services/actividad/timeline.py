"""
Timeline de actividad empresarial (Fase 3, SUBFASE 3.1/3.10).

El Centro de Actividad no es una lista de mensajes: es la linea de tiempo de TODOS los
eventos del ERP. Cada entrada trae hora, terminal/origen, tipo legible, un resumen y el
estado de aplicacion (pendiente/aplicado) derivado de la distribucion. Preparado para que
una IA empresarial consulte y resuma la actividad (3.10).
"""

import json
import logging

from src.services.actividad import scope

logger = logging.getLogger("actividad.timeline")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def _legible(tipo):
    try:
        from src.services.eventos import tipos as _T
        v = _T.CATALOGO.get(tipo)
        if v:
            return v[1]
    except Exception:
        pass
    return str(tipo or "").replace("_", " ").capitalize()


def _resumen(payload_raw):
    if not payload_raw:
        return ""
    try:
        p = payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw)
    except Exception:
        return str(payload_raw)[:80]
    partes = []
    for k in ("codigo", "nombre", "referencia", "total", "importe", "precio", "cantidad",
              "metodo", "tipo", "motivo"):
        if k in p and p[k] not in (None, ""):
            partes.append(f"{k}: {p[k]}")
    return " · ".join(partes[:4]) or (str(p)[:80])


def _estado_actividad(destinos, confirmados):
    d = int(destinos or 0); cnf = int(confirmados or 0)
    if d <= 0:
        return "Registrado"
    if cnf >= d:
        return "Aplicado"
    return "Pendiente de aplicar"


def feed(usuario=None, perfil=None, id_empresa=None, *, tipo=None, tipos=None, prioridad=None,
         id_tienda=None, usuario_filtro=None, desde=None, desde_id=None, limite=100) -> list:
    """Linea de tiempo de actividad (mas reciente primero) filtrada por alcance del usuario.

    Soporta paginacion KEYSET (`desde_id`: devuelve eventos con id < desde_id) para lazy-loading
    eficiente con millones de eventos, y filtro por conjunto de `tipos` (categorias rapidas)."""
    emp = _emp(id_empresa)
    if isinstance(usuario, dict) and perfil is None:
        perfil = usuario.get("perfil")
    frag, params = scope.filtro_sql(usuario, perfil, alias="e")
    q = ("SELECT e.id, e.uuid, e.fecha_creacion, e.tipo, e.origen, e.usuario, e.prioridad, "
         "e.id_tienda, e.payload, COUNT(d.id) AS destinos, "
         "COALESCE(SUM(d.estado='CONFIRMADO'),0) AS confirmados "
         "FROM eventos e LEFT JOIN distribucion_pendiente d "
         "  ON d.id_evento=e.id AND d.id_empresa=e.id_empresa "
         "WHERE e.id_empresa=%s")
    p = [emp]
    if tipo:
        q += " AND e.tipo=%s"; p.append(tipo)
    if tipos:
        marcas = ",".join(["%s"] * len(tipos))
        q += f" AND e.tipo IN ({marcas})"; p += list(tipos)
    if prioridad:
        q += " AND e.prioridad=%s"; p.append(prioridad)
    if id_tienda is not None:
        q += " AND e.id_tienda=%s"; p.append(int(id_tienda))
    if usuario_filtro:
        q += " AND e.usuario=%s"; p.append(str(usuario_filtro))
    if desde:
        q += " AND e.fecha_creacion>=%s"; p.append(desde)
    if desde_id:
        q += " AND e.id<%s"; p.append(int(desde_id))
    if frag:
        q += " AND " + frag; p += params
    q += " GROUP BY e.id ORDER BY e.id DESC LIMIT %s"; p.append(int(limite))

    filas = []
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(q, p)
            for r in cur.fetchall():
                g = (lambda i, k: r[i] if not isinstance(r, dict) else r[k])
                origen = g(4, "origen") or "-"
                filas.append({
                    "id": g(0, "id"), "uuid": g(1, "uuid"), "fecha": g(2, "fecha_creacion"),
                    "tipo": g(3, "tipo"), "tipo_legible": _legible(g(3, "tipo")),
                    "origen": origen, "terminal": ("CENTRAL" if str(origen).lower() == "central"
                                                   else str(origen).upper()),
                    "usuario": g(5, "usuario"), "prioridad": g(6, "prioridad"),
                    "id_tienda": g(7, "id_tienda"), "resumen": _resumen(g(8, "payload")),
                    "estado": _estado_actividad(g(9, "destinos"), g(10, "confirmados")),
                })
    except Exception as e:
        logger.error("feed: %s", e)
    return filas


def resumen_por_tipo(usuario=None, perfil=None, id_empresa=None, *, dias=7) -> list:
    """Agrupacion para la IA/dashboard: [{tipo, tipo_legible, total, pendientes}] ultimos N dias."""
    emp = _emp(id_empresa)
    if isinstance(usuario, dict) and perfil is None:
        perfil = usuario.get("perfil")
    frag, params = scope.filtro_sql(usuario, perfil, alias="e")
    q = ("SELECT e.tipo, COUNT(DISTINCT e.id) total, "
         "SUM(CASE WHEN d.estado IS NOT NULL AND d.estado<>'CONFIRMADO' THEN 1 ELSE 0 END) pend "
         "FROM eventos e LEFT JOIN distribucion_pendiente d "
         "  ON d.id_evento=e.id AND d.id_empresa=e.id_empresa "
         f"WHERE e.id_empresa=%s AND e.fecha_creacion >= (NOW() - INTERVAL {int(dias)} DAY)")
    p = [emp]
    if frag:
        q += " AND " + frag; p += params
    q += " GROUP BY e.tipo ORDER BY total DESC"
    out = []
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(q, p)
            for r in cur.fetchall():
                g = (lambda i, k: r[i] if not isinstance(r, dict) else r[k])
                out.append({"tipo": g(0, "tipo"), "tipo_legible": _legible(g(0, "tipo")),
                            "total": int(g(1, "total") or 0), "pendientes": int(g(2, "pend") or 0)})
    except Exception as e:
        logger.error("resumen_por_tipo: %s", e)
    return out
