"""
Estado global de la CUENTA (progreso de configuración) — vista única y honesta.

NO crea datos ni motores nuevos (N7): AGREGA lo que ya calculan otros módulos para responder "¿cuánto me
falta para tener la cuenta configurada al 100%?":
  · Datos de empresa (`onboarding.datos_empresa_incompletos`).
  · Edición elegida (`verticales.edicion_definida`).
  · Asistente de bienvenida (`onboarding.completado`).
  · Plan / suscripción (`saas.licensing` / `saas.suscripciones`).
  · Integraciones de PRODUCCIÓN (`integraciones.activacion`) — OPCIONALES (requieren credenciales de
    coste): se muestran como preparación, NO penalizan el % de configuración base.

Best-effort y degradable: cualquier fuente que falle no rompe el resumen (se marca como pendiente).
Lo consume la pestaña "ESTADO DE LA CUENTA" de Configuración.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("cuenta.estado")


def _emp(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _item_datos_empresa(emp) -> dict:
    hecho, detalle = False, "Completa el nombre fiscal y el CIF de la empresa."
    try:
        from src.services import onboarding
        hecho = not onboarding.datos_empresa_incompletos(emp)
        if hecho:
            detalle = "Nombre fiscal y CIF configurados."
    except Exception as e:
        logger.debug("_item_datos_empresa: %s", e)
    return {"clave": "datos_empresa", "titulo": "Datos de empresa", "hecho": hecho,
            "detalle": detalle, "accion": "Configuración › Datos de empresa"}


def _item_edicion(emp) -> dict:
    hecho, detalle = False, "Elige el tipo de comercio (edición) de tu negocio."
    try:
        from src.services import verticales
        hecho = bool(verticales.edicion_definida())
        if hecho:
            detalle = f"Edición: {verticales.nombre_edicion()}."
    except Exception as e:
        logger.debug("_item_edicion: %s", e)
    return {"clave": "edicion", "titulo": "Edición elegida", "hecho": hecho,
            "detalle": detalle, "accion": "Configuración › Versión"}


def _item_asistente(emp) -> dict:
    hecho, detalle = False, "Completa el asistente de bienvenida (primeros pasos)."
    try:
        from src.services import onboarding
        hecho = bool(onboarding.completado())
        if hecho:
            detalle = "Asistente de bienvenida completado."
    except Exception as e:
        logger.debug("_item_asistente: %s", e)
    return {"clave": "asistente", "titulo": "Primeros pasos", "hecho": hecho,
            "detalle": detalle, "accion": "Menú › Primeros pasos"}


def _item_plan(emp) -> dict:
    hecho, detalle = False, "Activa un plan de suscripción."
    plan = None
    try:
        from src.services.saas import licensing as _L
        lic = _L.licencia_activa(emp)
        if lic:
            plan = lic.get("codigo_plan")
            hecho = str(lic.get("estado") or "").lower() in ("activa", "activo", "trial", "prueba")
            detalle = f"Plan {plan} · {lic.get('estado')}"
    except Exception as e:
        logger.debug("_item_plan: %s", e)
    return {"clave": "plan", "titulo": "Plan / suscripción", "hecho": hecho,
            "detalle": detalle, "accion": "Suscripción › Mi plan", "plan": plan}


# Ítems CORE que cuentan para el % de configuración de la cuenta (los de producción NO cuentan).
_ITEMS_CORE = (_item_datos_empresa, _item_edicion, _item_asistente, _item_plan)


def resumen(id_empresa=None) -> dict:
    """Estado global de la cuenta. Devuelve:
    {porcentaje, completado, items:[...core...], pendientes:[titulos], integraciones:{...}, edicion, plan}.
    El `porcentaje` mide solo los ítems CORE; las integraciones de producción se listan aparte (opcionales)."""
    emp = _emp(id_empresa)
    items = []
    for fn in _ITEMS_CORE:
        try:
            items.append(fn(emp))
        except Exception as e:
            logger.debug("item core %s: %s", getattr(fn, "__name__", "?"), e)
    total = len(items) or 1
    hechos = sum(1 for it in items if it.get("hecho"))
    porcentaje = int(round(100 * hechos / total))
    pendientes = [it["titulo"] for it in items if not it.get("hecho")]

    integraciones = {"total": 0, "en_produccion": [], "preparadas": [], "detalle": []}
    try:
        from src.services.integraciones import activacion
        integraciones = activacion.resumen(emp)
    except Exception as e:
        logger.debug("integraciones: %s", e)

    edicion = None
    try:
        from src.services import verticales
        edicion = verticales.nombre_edicion() if verticales.edicion_definida() else None
    except Exception:
        pass
    plan = next((it.get("plan") for it in items if it.get("clave") == "plan"), None)

    return {"porcentaje": porcentaje, "completado": porcentaje >= 100, "hechos": hechos, "total": total,
            "items": items, "pendientes": pendientes, "integraciones": integraciones,
            "edicion": edicion, "plan": plan}


__all__ = ["resumen"]
