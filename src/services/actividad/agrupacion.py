"""
Agrupacion inteligente y colapsado automatico del timeline (Paquete Enterprise 2,
SUBFASE 2.1/2.2/2.12).

Convierte cientos de eventos similares en una unica linea resumen expandible
("Se actualizaron 38 precios") SIN eliminar informacion (solo cambia la visualizacion).
Reutiliza el timeline del Centro de Actividad; no duplica consultas ni logica.
"""

import logging

from src.services.actividad import filtros, timeline

logger = logging.getLogger("actividad.agrupacion")

UMBRAL_DEFECTO = 5   # SUBFASE 2.2: hasta 5 individuales; mas de 5 → colapsar (configurable)

# Plantillas de resumen por tipo ("{n}" = numero de eventos del grupo).
_PLANTILLAS = {
    "PRECIO_ACTUALIZADO": "Se actualizaron {n} precios",
    "PROMOCION_PUBLICADA": "{n} promociones publicadas",
    "VENTA_REGISTRADA": "{n} ventas registradas",
    "FACTURA_GENERADA": "{n} facturas generadas",
    "FACTURA_ANULADA": "{n} facturas anuladas",
    "COBRO_REGISTRADO": "{n} cobros registrados",
    "PEDIDO_RECIBIDO": "{n} pedidos recibidos",
    "KARDEX_MOVIMIENTO": "{n} movimientos de stock",
    "INVENTARIO_CORREGIDO": "{n} ajustes de inventario",
    "MERMA_REGISTRADA": "{n} mermas registradas",
    "REPOSICION_GENERADA": "{n} propuestas de reposicion",
    "CLIENTE_CREADO": "{n} clientes creados",
    "NOMINA_GENERADA": "{n} nominas generadas",
    "DOCUMENTO_PUBLICADO": "{n} documentos publicados",
    "CORREO_RECIBIDO": "{n} correos recibidos",
    "WORKFLOW_INICIADO": "{n} circuitos de workflow iniciados",
}


def _clave(ev, por):
    if por == "usuario":
        return ev.get("usuario") or "—"
    if por == "tienda":
        return ev.get("id_tienda")
    if por == "modulo":
        return ev.get("origen") or "—"
    if por == "prioridad":
        return ev.get("prioridad") or "MEDIA"
    if por == "intervalo":
        return str(ev.get("fecha") or "")[:13]   # bucket por hora
    return ev.get("tipo")                          # por tipo (defecto)


def _resumen(tipo, tipo_legible, n) -> str:
    pl = _PLANTILLAS.get(str(tipo).upper())
    if pl:
        return pl.format(n=n)
    return f"{n} × {tipo_legible}"


def agrupar(eventos, *, por="tipo", umbral=UMBRAL_DEFECTO) -> list:
    """Agrupa una lista de eventos. Devuelve nodos: eventos individuales (kind='evento') o
    grupos colapsados (kind='grupo') expandibles. Preserva el orden cronologico del grupo."""
    grupos, orden = {}, []
    for ev in eventos:
        k = _clave(ev, por)
        if k not in grupos:
            grupos[k] = []
            orden.append(k)
        grupos[k].append(ev)
    nodos = []
    for k in orden:
        items = grupos[k]
        if len(items) <= umbral:
            for ev in items:
                nodos.append({"kind": "evento", **ev})
        else:
            primero = items[0]
            nodos.append({
                "kind": "grupo", "clave": k, "por": por, "count": len(items),
                "tipo": primero.get("tipo"),
                "resumen": _resumen(primero.get("tipo"), primero.get("tipo_legible"), len(items)),
                "prioridad": primero.get("prioridad"),
                "fecha": primero.get("fecha"),
                "items": items,   # nunca se pierde informacion
            })
    # Orden global por fecha del primer elemento (mas reciente primero).
    nodos.sort(key=lambda nd: str(nd.get("fecha") or ""), reverse=True)
    return nodos


def feed_agrupado(usuario=None, perfil=None, id_empresa=None, *, categoria=None, por="tipo",
                  umbral=UMBRAL_DEFECTO, prioridad=None, id_tienda=None, usuario_filtro=None,
                  desde_id=None, limite=200) -> dict:
    """Timeline agrupado por separadores temporales (Hoy/Ayer/...) y colapsado por `por`.
    Paginacion keyset (desde_id) para lazy-loading (SUBFASE 2.11)."""
    tipos = filtros.tipos_de_categoria(categoria)
    evs = timeline.feed(usuario, perfil, id_empresa, tipos=tipos, prioridad=prioridad,
                        id_tienda=id_tienda, usuario_filtro=usuario_filtro, desde_id=desde_id,
                        limite=limite)
    # Bucket temporal preservando orden.
    buckets, orden = {}, []
    for ev in evs:
        sep = filtros.separador_temporal(ev.get("fecha"))
        if sep not in buckets:
            buckets[sep] = []
            orden.append(sep)
        buckets[sep].append(ev)
    secciones = [{"separador": sep, "nodos": agrupar(buckets[sep], por=por, umbral=umbral)}
                 for sep in orden]
    ultimo_id = evs[-1]["id"] if evs else None
    return {"secciones": secciones, "ultimo_id": ultimo_id, "total_eventos": len(evs),
            "hay_mas": len(evs) >= limite}


def resumen_ejecutivo(id_empresa=None, *, usuario=None, perfil=None, dias=1) -> list:
    """Recuento AGRUPADO por tipo (SUBFASE 2.12): la IA responde "¿que ha pasado hoy?" sin
    recorrer millones de eventos, reutilizando la agregacion del Centro de Actividad."""
    return timeline.resumen_por_tipo(usuario, perfil, id_empresa, dias=dias)
