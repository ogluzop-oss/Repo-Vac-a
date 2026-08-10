"""
Cloud Manager · Licencias (Fase V · Bloque 7). Planes SaaS (Enterprise/Professional/Basic/Trial/
Personalizadas) REUTILIZANDO `services.saas.licensing` y `services.saas.planes` (no crea un segundo
sistema de licenciamiento). Multiempresa.
"""

from __future__ import annotations

PLANES = ("enterprise", "professional", "basic", "trial", "custom")


def asignar(id_empresa, plan, *, usuario=None) -> dict:
    if plan not in PLANES:
        return {"ok": False, "error": f"plan no válido: {plan}"}
    try:
        from src.services.saas import licensing
        ok = licensing.asignar_plan(id_empresa, plan, estado="activa", usuario=usuario)
        return {"ok": bool(ok), "id_empresa": id_empresa, "plan": plan}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def estado(id_empresa=None) -> dict:
    try:
        from src.services.saas import licensing
        lic = licensing.licencia_activa(id_empresa) or {}
        return {"licencia": lic, "operativo": licensing.estado_operativo(id_empresa)}
    except Exception as e:
        return {"error": str(e)}


def limite(recurso, id_empresa=None) -> dict:
    try:
        from src.services.saas import licensing
        return licensing.limite_disponible(recurso, id_empresa)
    except Exception as e:
        return {"error": str(e)}


def descriptor() -> dict:
    return {"planes": list(PLANES), "fuente": "saas.licensing"}


__all__ = ["PLANES", "asignar", "estado", "limite", "descriptor"]
