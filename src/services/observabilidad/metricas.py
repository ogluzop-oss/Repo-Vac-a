"""
Métricas técnicas (OBS-4).

Usa prometheus_client si está instalado (Counter/Gauge/Histogram + render exposition format);
si no, degrada a contadores en memoria con un render de texto compatible. API estable:
inc(nombre), observe(nombre, valor), set_gauge(nombre, valor), render() → texto Prometheus.
"""

import logging
import time

logger = logging.getLogger("obs.metricas")

try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest, CollectorRegistry
    _PROM = True
    _REG = CollectorRegistry()
    _C, _G, _H = {}, {}, {}
except Exception:
    _PROM = False
    _MEM = {"counters": {}, "gauges": {}, "hist": {}}


def inc(nombre, valor=1, etiqueta=None):
    clave = f"{nombre}" + (f'_{etiqueta}' if etiqueta else "")
    if _PROM:
        c = _C.get(nombre)
        if c is None:
            c = _C[nombre] = Counter(nombre, nombre, registry=_REG)
        c.inc(valor)
    else:
        _MEM["counters"][clave] = _MEM["counters"].get(clave, 0) + valor


def set_gauge(nombre, valor):
    if _PROM:
        g = _G.get(nombre)
        if g is None:
            g = _G[nombre] = Gauge(nombre, nombre, registry=_REG)
        g.set(valor)
    else:
        _MEM["gauges"][nombre] = valor


def observe(nombre, valor):
    if _PROM:
        h = _H.get(nombre)
        if h is None:
            h = _H[nombre] = Histogram(nombre, nombre, registry=_REG)
        h.observe(valor)
    else:
        d = _MEM["hist"].setdefault(nombre, {"sum": 0.0, "count": 0})
        d["sum"] += valor; d["count"] += 1


def timer(nombre):
    """Context manager que mide latencia en segundos y la registra como histograma."""
    class _T:
        def __enter__(self_):
            self_.t = time.perf_counter(); return self_
        def __exit__(self_, *a):
            observe(nombre, time.perf_counter() - self_.t)
    return _T()


def actualizar_negocio(id_empresa=None):
    """Refresca gauges de negocio (tenants/licencias/pagos) desde los servicios SaaS."""
    try:
        from src.services.saas import metricas as _sm
        m = _sm.resumen()
        set_gauge("sm_tenants_activos", m.get("empresas_activas", 0))
        set_gauge("sm_usuarios_activos", m.get("usuarios_activos", 0))
        set_gauge("sm_mrr_eur", m.get("mrr", 0))
    except Exception as e:
        logger.debug("actualizar_negocio: %s", e)


def render() -> str:
    if _PROM:
        try:
            return generate_latest(_REG).decode("utf-8")
        except Exception as e:
            return f"# error: {e}\n"
    out = []
    for k, v in _MEM["counters"].items():
        out.append(f"{k} {v}")
    for k, v in _MEM["gauges"].items():
        out.append(f"{k} {v}")
    for k, d in _MEM["hist"].items():
        out.append(f"{k}_sum {d['sum']}"); out.append(f"{k}_count {d['count']}")
    return "\n".join(out) + "\n"
