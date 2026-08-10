"""
Centro de Integraciones · COLA DE TRABAJOS (Fase WEB-16.5).

Reutiliza la **cola local** del motor WEB-13 (`motor.cola('local')`) para los trabajos PENDIENTES y lleva el
ciclo `pendiente → sincronizando → completado/fallido`. NO usa Redis/SQS/AWS: cuando llegue esa fase, basta
cambiar el backend (`motor.cola('sqs')`) sin tocar el negocio ni la UI. Sin polling ni jobs programados.
"""

import itertools
import time

_SEQ = itertools.count(1)
_JOBS = []                     # historial de trabajos de la sesión (todos los estados)


def _cola():
    from src.services.marketplace.integraciones_comerciales import motor
    return motor.cola("local")   # backend intercambiable (local → sqs en el futuro), sin tocar esto


_Q = None


def _q():
    global _Q
    if _Q is None:
        _Q = _cola()
    return _Q


def encolar(id_empresa, plataforma, tipo="sincronizar") -> dict:
    """Añade un trabajo PENDIENTE a la cola local."""
    job = {"id": next(_SEQ), "id_empresa": str(id_empresa), "plataforma": plataforma, "tipo": tipo,
           "estado": "pendiente", "creado": time.time(), "resultado": None}
    _JOBS.append(job)
    _q().encolar(job)
    return job


def ejecutar_pendientes(runner) -> list:
    """Ejecuta los pendientes de la cola local. `runner(job) -> (ok, resultado)`. Marca el ciclo de estado.
    Ejecución local/síncrona (el modo asíncrono real llega con el backend remoto)."""
    hechos = []
    q = _q()
    while q.tamano():
        job = q.desencolar()
        if not job:
            break
        job["estado"] = "sincronizando"
        try:
            ok, res = runner(job)
            job["estado"] = "completado" if ok else "fallido"
            job["resultado"] = res
        except Exception as e:
            job["estado"] = "fallido"
            job["resultado"] = {"error": str(e)}
        hechos.append(job)
    return hechos


def resumen() -> dict:
    """Contadores por estado (pendientes/sincronizando/completados/fallidos)."""
    from collections import Counter
    c = Counter(j["estado"] for j in _JOBS)
    return {"pendientes": c.get("pendiente", 0), "sincronizando": c.get("sincronizando", 0),
            "completados": c.get("completado", 0), "fallidos": c.get("fallido", 0)}


def listar(limite=100) -> list:
    return list(reversed(_JOBS))[:limite]


def _reset():
    _JOBS.clear()
    q = _q()
    while q.tamano():
        q.desencolar()
