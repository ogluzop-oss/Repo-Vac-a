"""
Etapa C · Fase C5 — Aprendizaje continuo SUPERVISADO (Área 10).

Prepara la arquitectura para que la inteligencia MEJORE sus recomendaciones usando el histórico y el
feedback humano (aceptaciones/rechazos/valoraciones) — SIEMPRE supervisado y SIN modificar datos de
negocio ni reentrenar automáticamente. Calcula un `ranking` de utilidad por origen/tipo a partir del
ledger `decisiones_ia` (C1) y permite `priorizar` decisiones aplicando ese aprendizaje. Solo lectura,
RBAC (`inteligencia.ver`), multiempresa, degradable. No crea tablas ni motores nuevos.
"""

from __future__ import annotations

import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("inteligencia.aprendizaje")

FASE = "C5"

_PRIORIDAD_ORD = {"ALTA": 0, "MEDIA": 1, "BAJA": 2, "INFO": 3}


def _emp(id_empresa=None):
    from src.services import inteligencia
    return inteligencia._emp(id_empresa)


def _puede(usuario, emp):
    from src.services import inteligencia
    return inteligencia._puede(usuario, "inteligencia.ver", emp)


def ranking(id_empresa=None, *, por="origen", usuario=None):
    """Utilidad histórica por `origen` (o `tipo`) derivada del feedback humano: utilidad = (aceptadas +
    feedback útil) / resueltas. Rango 0..1 (mayor = históricamente más útil). Supervisado."""
    if por not in ("origen", "tipo", "dominio"):
        por = "origen"
    emp = _emp(id_empresa)
    if not _puede(usuario, emp):
        return {}
    out = {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {por}, "
                "SUM(estado='aceptada') AS aceptadas, "
                "SUM(estado='rechazada') AS rechazadas, "
                "SUM(feedback LIKE 'util=True%%') AS feedback_util "
                "FROM decisiones_ia WHERE id_empresa=%s AND estado IN ('aceptada','rechazada') "
                f"GROUP BY {por}", (emp,))
            for f in cur.fetchall():
                vals = list(f.values()) if isinstance(f, dict) else list(f)
                clave, acc, rej, fbu = vals[0], int(vals[1] or 0), int(vals[2] or 0), int(vals[3] or 0)
                resueltas = acc + rej
                if resueltas <= 0:
                    continue
                utilidad = round(min(1.0, (acc + fbu) / (resueltas + fbu if fbu else resueltas)), 3)
                out[clave] = {"resueltas": resueltas, "aceptadas": acc, "rechazadas": rej,
                              "feedback_util": fbu, "utilidad": utilidad}
    except Exception as e:
        logger.error("ranking: %s", e)
    return out


def priorizar(decisiones, id_empresa=None, *, por="origen", usuario=None):
    """Reordena una lista de decisiones aplicando el aprendizaje: primero por prioridad y luego por la
    utilidad histórica de su `origen`/`tipo`. NO modifica datos: devuelve una lista reordenada."""
    emp = _emp(id_empresa)
    rk = ranking(emp, por=por, usuario=usuario)

    def _peso(d):
        util = (rk.get(d.get(por)) or {}).get("utilidad", 0.0)
        return (_PRIORIDAD_ORD.get(d.get("prioridad"), 9), -util)

    return sorted(list(decisiones or []), key=_peso)


def recomendar_ordenado(id_empresa=None, *, usuario=None, tipo="recomendacion", limite=20):
    """Recomendaciones abiertas ordenadas por el aprendizaje (prioridad + utilidad histórica). Combina
    el Centro de Decisiones (C1) con el ranking supervisado. Solo lectura."""
    from src.services import inteligencia
    emp = _emp(id_empresa)
    decs = inteligencia.decisiones(emp, tipo=tipo, usuario=usuario, limite=200)
    return priorizar(decs, emp, por="origen", usuario=usuario)[:limite]


def descriptor() -> dict:
    return {"servicio": "inteligencia.aprendizaje", "etapa": "C", "fase": FASE,
            "estado": "implementado", "supervisado": True, "reentrena_auto": False,
            "modifica_datos": False, "reutiliza": ["decisiones_ia (feedback humano)", "inteligencia"],
            "motor_nuevo": False}


__all__ = ["FASE", "ranking", "priorizar", "recomendar_ordenado", "descriptor"]
