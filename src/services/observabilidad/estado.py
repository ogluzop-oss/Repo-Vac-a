"""
Observabilidad · Estado operacional unificado (Etapa F · Fase F2).

Fachada que COMPONE las piezas de salud/diagnóstico YA EXISTENTES en una vista operacional única, sin
crear mecanismos nuevos (Reglas 6/7): liveness/readiness/health (`observabilidad.health`), foto del
sistema (`utils.observabilidad.estado_sistema`), gauges operacionales (`observabilidad.operacional`, F1),
diagnóstico de resiliencia (`resiliencia.resilience_watchdog.diagnosticar`) y estado por tenant del
Gemelo Digital (`gemelo`, degradable).

Expone: `self_test`, `diagnostico`, `global_`/`sistema`, `por_modulo`, `por_tenant`. Solo lectura,
multiempresa, degradable. Aditivo y retrocompatible.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("observabilidad.estado")

FASE = "F2"


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _health():
    try:
        from src.services.observabilidad import health
        return health
    except Exception:
        return None


def global_() -> dict:
    """Estado GLOBAL del sistema: liveness/readiness/health por subsistema + foto del sistema."""
    h = _health()
    salud = h.health() if h else {"status": "unknown", "subsistemas": {}}
    ready = h.ready() if h else {"status": "unknown"}
    live = h.live() if h else {"status": "unknown"}
    sistema = {}
    try:
        from src.utils import observabilidad as _obs
        sistema = _obs.estado_sistema()
    except Exception as e:
        logger.debug("estado_sistema: %s", e)
    return {"status": salud.get("status", "unknown"), "live": live, "ready": ready,
            "subsistemas": salud.get("subsistemas", {}), "sistema": sistema}


def sistema() -> dict:
    """Alias de `global_()` (estado global del sistema)."""
    return global_()


def por_modulo(id_empresa=None) -> dict:
    """Estado POR MÓDULO: subsistemas de `health` + métricas operacionales por subsistema (F1)."""
    h = _health()
    subs = (h.health().get("subsistemas", {}) if h else {}) or {}
    modulos = {}
    for k, v in subs.items():
        modulos[k] = {"ok": v if isinstance(v, bool) else None, "fuente": "health"}
    try:
        from src.services.observabilidad import operacional
        for k, v in operacional.snapshot(id_empresa).items():
            entrada = modulos.setdefault(k, {"ok": True, "fuente": "operacional"})
            entrada["metricas"] = v
            entrada.setdefault("ok", True)
    except Exception as e:
        logger.debug("por_modulo operacional: %s", e)
    return modulos


def por_tenant(id_empresa=None) -> dict:
    """Estado POR TENANT: readiness global + métricas operacionales del tenant + (si disponible) el
    estado ejecutivo del Gemelo Digital. Degradable."""
    emp = _emp(id_empresa)
    h = _health()
    out = {"id_empresa": emp, "ready": (h.ready() if h else {"status": "unknown"})}
    try:
        from src.services.observabilidad import operacional
        out["operacional"] = operacional.snapshot(emp)
    except Exception as e:
        logger.debug("por_tenant operacional: %s", e)
    try:
        from src.services import gemelo
        if hasattr(gemelo, "estado_global"):
            g = gemelo.estado_global(emp)
            out["gemelo"] = {"riesgo_global": g.get("riesgo_global"), "resumen": g.get("resumen"),
                             "alertas": len(g.get("alertas", []))}
    except Exception as e:
        logger.debug("por_tenant gemelo: %s", e)
    return out


def self_test(id_empresa=None) -> dict:
    """Batería de auto-pruebas reutilizando las comprobaciones existentes. Devuelve `{ok, checks}`.
    `ok` es True si todos los checks CRÍTICOS pasan (db/health)."""
    emp = _emp(id_empresa)
    checks = []

    def _add(nombre, ok, detalle="", critico=False):
        checks.append({"nombre": nombre, "ok": bool(ok), "detalle": detalle, "critico": critico})

    h = _health()
    ready = h.ready() if h else {"db": False}
    _add("db_accesible", ready.get("db"), "SELECT 1", critico=True)

    salud = h.health() if h else {"status": "unknown", "subsistemas": {}}
    _add("health_global", salud.get("status") in ("ok", "degraded"), salud.get("status", ""), critico=True)
    for k, v in (salud.get("subsistemas", {}) or {}).items():
        if isinstance(v, bool):
            _add(f"subsistema_{k}", v, "")

    try:
        from src.utils import observabilidad as _obs
        est = _obs.estado_sistema()
        _add("migracion", bool(est.get("migracion_actual")), str(est.get("migracion_actual")))
        _add("backups", bool(est.get("backups")), "")
    except Exception as e:
        _add("estado_sistema", False, str(e))

    try:
        from src.services.observabilidad import operacional
        snap = operacional.snapshot(emp)
        for modulo in ("scheduler", "eventbus", "marketplace", "sdk"):
            _add(f"operacional_{modulo}", isinstance(snap.get(modulo), dict), "")
    except Exception as e:
        _add("operacional", False, str(e))

    criticos_ok = all(c["ok"] for c in checks if c["critico"])
    return {"ok": criticos_ok, "id_empresa": emp,
            "total": len(checks), "fallidos": [c["nombre"] for c in checks if not c["ok"]],
            "checks": checks}


def diagnostico(id_empresa=None) -> dict:
    """Diagnóstico operacional: reutiliza el watchdog de resiliencia (subsistemas+colas+breakers+sync),
    la foto del sistema y el texto de diagnóstico existentes. Degradable."""
    emp = _emp(id_empresa)
    diag = {"id_empresa": emp}
    try:
        from src.services.resiliencia import resilience_watchdog
        diag["resiliencia"] = resilience_watchdog.diagnosticar(id_empresa=emp)
    except Exception as e:
        logger.debug("diagnostico resiliencia: %s", e)
    try:
        from src.utils import observabilidad as _obs
        diag["sistema"] = _obs.estado_sistema()
        if hasattr(_obs, "diagnostico_texto"):
            diag["texto"] = _obs.diagnostico_texto()
    except Exception as e:
        logger.debug("diagnostico sistema: %s", e)
    return diag


def descriptor() -> dict:
    return {"servicio": "observabilidad.estado", "etapa": "F", "fase": FASE,
            "estado": "implementado", "solo_lectura": True, "motor_nuevo": False,
            "reutiliza": ["observabilidad.health", "utils.observabilidad.estado_sistema",
                          "observabilidad.operacional (F1)", "resiliencia.resilience_watchdog",
                          "gemelo (degradable)"],
            "operaciones": ["self_test", "diagnostico", "global_", "por_modulo", "por_tenant"]}


__all__ = ["FASE", "self_test", "diagnostico", "global_", "sistema", "por_modulo", "por_tenant",
           "descriptor"]
