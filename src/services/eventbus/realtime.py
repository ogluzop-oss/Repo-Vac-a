"""
Hub de TIEMPO REAL EN RED. Puente 1:1 sobre el Event Bus EXISTENTE (no es un segundo bus): se suscribe una
sola vez a `services.eventos.bus` con comodín `"*"` y reparte los eventos REALES a los clientes conectados
(colas), SIEMPRE con AISLAMIENTO POR TENANT (`id_empresa` del evento). El transporte HTTP (SSE) vive en
`api/routers/realtime.py` y consume este hub. NO crea eventos, NO persiste, NO duplica lógica (N7).

Alcance: SINGLE-INSTANCE (en memoria, event-driven, sin polling). Para MULTI-INSTANCIA se necesita un broker
distribuido (Redis/NATS/…): el punto de extensión es `set_distribucion()` — PREPARADO_PARA_DISTRIBUCION,
[EXTERNO — REQUIERE PROVISIONADO REAL]. No se activa ni se simula.
"""

import logging
import queue
import threading

logger = logging.getLogger("eventbus.realtime")

_LOCK = threading.RLock()
_CLIENTES: dict = {}      # id -> _Cliente
_SUSCRITO = False
_SEQ = 0
_METRICAS = {"conexiones_totales": 0, "activas": 0, "eventos_repartidos": 0, "descartes_cola_llena": 0}
_MAX_COLA = 1000


class _Cliente:
    """Un consumidor conectado: cola propia + tenant + filtro de canales."""
    __slots__ = ("id", "id_empresa", "id_tienda", "canales", "cola")

    def __init__(self, cid, id_empresa, id_tienda, canales):
        self.id = cid
        self.id_empresa = id_empresa
        self.id_tienda = id_tienda
        self.canales = canales            # set de prefijos de canal, o None = todos los del tenant
        self.cola = queue.Queue(maxsize=_MAX_COLA)


def _canal_de(tipo) -> str:
    """Canal funcional = primer segmento del tipo de evento ('stock.salida' → 'stock')."""
    return str(tipo or "").split(".")[0]


def _asegurar_suscripcion() -> None:
    """Se suscribe UNA vez al Event Bus existente (comodín '*'). Idempotente."""
    global _SUSCRITO
    if _SUSCRITO:
        return
    try:
        from src.services.eventos import bus
        bus.suscribir("*", _on_event)
        _SUSCRITO = True
        logger.info("realtime hub suscrito al Event Bus ('*').")
    except Exception as e:
        logger.debug("suscripcion bus: %s", e)


def _on_event(ev: dict, *, _remoto=False) -> None:
    """Handler del bus: `ev` es el dict del Evento real (id, uuid, tipo, id_empresa, id_tienda, …). Reparte
    SOLO a clientes del MISMO tenant (aislamiento estricto, nunca cross-tenant) y que escuchen ese canal.

    Multi-instancia (Fase 10): si hay un adaptador de distribución inyectado, los eventos LOCALES se propagan
    a las demás instancias (`_remoto=False`); los eventos que LLEGAN de otra instancia (`_remoto=True`) sólo se
    reparten a clientes locales y NO se reenvían (evita bucles). El aislamiento por tenant es idéntico en ambos
    casos: el `id_empresa` viaja en el evento y el filtro de reparto no cambia."""
    if not isinstance(ev, dict):
        try:
            ev = ev.to_dict()
        except Exception:
            return
    emp = ev.get("id_empresa")
    canal = _canal_de(ev.get("tipo"))
    if not _remoto and _DISTRIBUCION is not None:
        try:
            _DISTRIBUCION.publicar(ev)          # propaga a otras instancias (transport, NO segundo bus)
        except Exception as e:
            logger.debug("distribucion.publicar: %s", e)
    with _LOCK:
        objetivos = [c for c in _CLIENTES.values() if str(c.id_empresa) == str(emp)]
    for c in objetivos:
        if c.canales and canal not in c.canales:
            continue
        try:
            c.cola.put_nowait(ev)
            with _LOCK:
                _METRICAS["eventos_repartidos"] += 1
        except queue.Full:
            with _LOCK:
                _METRICAS["descartes_cola_llena"] += 1   # cliente lento → resincroniza al reconectar


def registrar(id_empresa, *, id_tienda=None, canales=None) -> _Cliente:
    """Alta de un cliente conectado (para su tenant). El `id_empresa` SIEMPRE viene del token, no del
    cliente. Devuelve el handle con su cola."""
    global _SEQ
    _asegurar_suscripcion()
    with _LOCK:
        _SEQ += 1
        c = _Cliente(_SEQ, id_empresa, id_tienda, set(canales) if canales else None)
        _CLIENTES[c.id] = c
        _METRICAS["conexiones_totales"] += 1
        _METRICAS["activas"] = len(_CLIENTES)
    return c


def desregistrar(cliente) -> None:
    with _LOCK:
        _CLIENTES.pop(getattr(cliente, "id", None), None)
        _METRICAS["activas"] = len(_CLIENTES)


def conexiones_de(id_empresa) -> int:
    """Nº de clientes conectados de un tenant (para métricas/tests)."""
    with _LOCK:
        return sum(1 for c in _CLIENTES.values() if str(c.id_empresa) == str(id_empresa))


def metricas() -> dict:
    with _LOCK:
        return dict(_METRICAS)


# ── Punto de extensión para MULTI-INSTANCIA (no activado; sin infraestructura no se simula) ──
_DISTRIBUCION = None


def set_distribucion(adaptador) -> None:
    """Inyecta un adaptador de distribución (Redis/NATS/…) para propagar eventos entre instancias. Debe
    exponer `publicar(ev)` y llamar a `_on_event` con los eventos remotos. PREPARADO_PARA_DISTRIBUCION;
    sin adaptador real, el hub opera en single-instance. NUNCA se declara multi-instancia sin prueba real."""
    global _DISTRIBUCION
    _DISTRIBUCION = adaptador
