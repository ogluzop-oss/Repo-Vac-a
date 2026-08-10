"""
Vista ejecutiva, por usuario y por tienda (Paquete Enterprise 2, SUBFASE 2.8/2.9/2.10).

Dashboard de tarjetas (Ventas 128 ↑, Pedidos 42 ↓...) con tendencia hoy vs ayer, y vistas de
actividad completas por empleado y por tienda. Todo agregado desde el Event Bus (no recorre
millones de eventos: usa GROUP BY indexado). Reutiliza timeline/sincronizacion.
"""

import logging

from src.services.actividad import filtros, sincronizacion, timeline

logger = logging.getLogger("actividad.ejecutiva")

# Tarjetas ejecutivas → categoria de filtros (conjunto de tipos).
_CARDS = [
    ("Ventas", "VENTAS"), ("Pedidos", "COMPRAS"), ("Facturas", "FACTURACION"),
    ("Inventario", "INVENTARIO"), ("Clientes", "CRM"), ("Cobros", "TESORERIA"),
    ("Precios", "CATALOGO"),
]


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


def _conteos_por_tipo(emp):
    """{tipo: (hoy, ayer)} en una sola consulta agregada."""
    out = {}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "SELECT tipo, "
                "SUM(DATE(fecha_creacion)=CURDATE()) hoy, "
                "SUM(DATE(fecha_creacion)=(CURDATE()-INTERVAL 1 DAY)) ayer "
                "FROM eventos WHERE id_empresa=%s AND fecha_creacion >= (CURDATE()-INTERVAL 1 DAY) "
                "GROUP BY tipo", (emp,))
            for r in cur.fetchall():
                g = (lambda i: r[i] if not isinstance(r, dict) else list(r.values())[i])
                out[g(0)] = (int(g(1) or 0), int(g(2) or 0))
    except Exception as e:
        logger.error("_conteos_por_tipo: %s", e)
    return out


def vista_ejecutiva(id_empresa=None, *, usuario=None, perfil=None) -> list:
    """Tarjetas: [{titulo, valor(hoy), tendencia(up/down/flat), ayer}]. SUBFASE 2.8."""
    emp = _emp(id_empresa)
    ct = _conteos_por_tipo(emp)
    tarjetas = []
    for titulo, cat in _CARDS:
        tipos = filtros.tipos_de_categoria(cat) or ()
        hoy = sum(ct.get(t, (0, 0))[0] for t in tipos)
        ayer = sum(ct.get(t, (0, 0))[1] for t in tipos)
        tend = "up" if hoy > ayer else ("down" if hoy < ayer else "flat")
        tarjetas.append({"titulo": titulo, "valor": hoy, "ayer": ayer, "tendencia": tend})
    # Terminales offline (desde el panel de sincronizacion).
    try:
        panel = sincronizacion.panel(emp)
        off = len([t for t in panel if str(t.get("estado")).upper() == "OFFLINE"])
        tarjetas.append({"titulo": "Offline", "valor": off, "ayer": None,
                         "tendencia": "down" if off else "flat"})
    except Exception:
        pass
    return tarjetas


def actividad_usuario(empleado, id_empresa=None, *, limite=100) -> list:
    """Todo lo que hizo un empleado (SUBFASE 2.9). Vista de administrador (alcance completo)."""
    return timeline.feed(None, "ADMINISTRADOR", id_empresa, usuario_filtro=str(empleado), limite=limite)


def actividad_tienda(id_tienda, id_empresa=None, *, limite=100) -> dict:
    """Vista completa de una tienda: actividad + estado de sincronizacion (SUBFASE 2.10)."""
    emp = _emp(id_empresa)
    feed = timeline.feed(None, "ADMINISTRADOR", emp, id_tienda=int(id_tienda), limite=limite)
    por_tipo = {}
    for ev in feed:
        por_tipo[ev.get("tipo")] = por_tipo.get(ev.get("tipo"), 0) + 1
    sync = None
    try:
        for t in sincronizacion.panel(emp):
            if int(t.get("id_tienda") or 0) == int(id_tienda):
                sync = t
                break
    except Exception:
        pass
    return {"id_tienda": int(id_tienda), "eventos": len(feed), "por_tipo": por_tipo,
            "sincronizacion": sync, "timeline": feed}
