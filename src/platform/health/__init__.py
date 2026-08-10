"""
Health checks de plataforma (Fase IV · Bloque 3). Agrega la salud de cada servicio registrado:
estado, versión, uptime, dependencias, latencia y último heartbeat. Reutiliza el health del núcleo
(`services.observabilidad.health`) para el subsistema base; nunca crea un sistema paralelo.
"""

from __future__ import annotations

import time

from src.platform import heartbeat, registry
from src.platform.contracts import HealthStatus


def _invocar_health(contrato) -> HealthStatus:
    inicio = time.time()
    estado, deps, version = "unknown", {}, contrato.version
    fn = contrato.health
    if callable(fn):
        try:
            r = fn()
            if isinstance(r, HealthStatus):
                r.latencia_ms = round((time.time() - inicio) * 1000, 2)
                return r
            if isinstance(r, dict):
                estado = r.get("status") or r.get("estado") or "ok"
                deps = r.get("subsistemas") or r.get("dependencias") or {}
                version = r.get("version") or version
            elif r:
                estado = "ok"
        except Exception:
            estado = "unavailable"
    else:
        estado = "ok"     # sin health propio: se asume vivo si está registrado
    e = registry.entrada(contrato.nombre) or {}
    return HealthStatus(estado=estado, version=version,
                        uptime_s=time.time() - e.get("registrado", time.time()),
                        dependencias=deps,
                        latencia_ms=round((time.time() - inicio) * 1000, 2),
                        ultimo_heartbeat=e.get("hb"))


def de_servicio(nombre) -> HealthStatus | None:
    c = registry.obtener(nombre)
    return _invocar_health(c) if c else None


def global_() -> dict:
    """Salud agregada de toda la plataforma."""
    servicios = {}
    estados = []
    for c in registry.listar():
        hs = _invocar_health(c)
        servicios[c.nombre] = hs.as_dict()
        estados.append(hs.estado)
    if not estados:
        estado = "unknown"
    elif all(e == "ok" for e in estados):
        estado = "ok"
    elif any(e == "unavailable" for e in estados):
        estado = "degraded"
    else:
        estado = "degraded"
    return {"estado": estado, "servicios": servicios,
            "stale": heartbeat.stale(), "total": len(servicios)}


__all__ = ["de_servicio", "global_"]
