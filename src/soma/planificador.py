"""
Planificador de SOMA (Fase 5). Ante una petición COMPLEJA, SOMA no responde de golpe: analiza, divide
el problema en pasos, propone un plan y pide confirmación antes de continuar. Reutiliza el Simulador
(impacto what-if) y la Autonomía Supervisada (ejecución gobernada) — nunca ejecuta por su cuenta.
"""

import logging

logger = logging.getLogger("soma.planificador")

# Intenciones complejas reconocidas → (claves, plan). El resto va al razonador/cerebro normal.
_PLANES = {
    "abrir_tienda": {
        "claves": (("abrir", "tienda"), ("nueva", "tienda"), ("montar", "tienda")),
        "titulo": "Plan para abrir una nueva tienda",
        "pasos": [
            "Estudiar ubicación, mercado y competencia.",
            "Estimar inversión inicial y costes recurrentes.",
            "Simular el impacto en ventas y beneficio (Simulador).",
            "Preparar un plan de ejecución gobernado (Autonomía Supervisada).",
        ],
        "simulacion": [{"variable": "tiendas", "valor": 1}],
    },
    "mejorar_ventas": {
        "claves": (("mejorar", "ventas"), ("subir", "ventas"), ("aumentar", "ventas")),
        "titulo": "Plan para mejorar las ventas",
        "pasos": [
            "Analizar ventas recientes y clientes activos/inactivos.",
            "Detectar oportunidades (Predicción y CRM).",
            "Proponer una campaña o promoción.",
            "Simular su impacto antes de lanzarla (Simulador).",
        ],
        "simulacion": [{"variable": "promocion", "valor": 10}],
    },
    "reducir_costes": {
        "claves": (("reducir", "costes"), ("bajar", "costes"), ("ahorrar",)),
        "titulo": "Plan para reducir costes",
        "pasos": [
            "Revisar gastos y márgenes actuales (Centro de Inteligencia).",
            "Comparar proveedores y condiciones (Compras).",
            "Simular el efecto de ajustar coste de proveedor (Simulador).",
            "Proponer medidas para tu aprobación.",
        ],
        "simulacion": [{"variable": "proveedor", "valor": -10}],
    },
}


def detectar(texto):
    """Devuelve la clave del plan si la petición es compleja; None si no."""
    t = (texto or "").lower()
    for clave, cfg in _PLANES.items():
        for grupo in cfg["claves"]:
            if all(k in t for k in grupo):
                return clave
    return None


def plan(clave) -> dict:
    cfg = _PLANES.get(clave)
    if not cfg:
        return {}
    pasos = "\n".join(f"  {i}. {p}" for i, p in enumerate(cfg["pasos"], 1))
    mensaje = (f"Antes de lanzarme, te propongo un plan:\n{pasos}\n"
               "¿Quieres que lo prepare? (sí / no)")
    return {"clave": clave, "titulo": cfg["titulo"], "pasos": cfg["pasos"], "mensaje": mensaje,
            "requiere_confirmacion": True, "simulacion": cfg.get("simulacion")}


def ejecutar_confirmado(clave, *, id_empresa=None) -> dict:
    """Tras la confirmación: reutiliza el Simulador (what-if, VIRTUAL) para anticipar el impacto y
    prepara el terreno. La ejecución REAL de acciones críticas seguiría por Autonomía/Workflow/Gobierno."""
    cfg = _PLANES.get(clave)
    if not cfg:
        return {"texto": "No tengo ese plan preparado."}
    sim = cfg.get("simulacion")
    if not sim:
        return {"texto": f"He preparado el plan «{cfg['titulo']}». Puedo profundizar en cualquier paso."}
    try:
        from src.services import simulador
        r = simulador.servicio().simular_directo(sim, id_empresa)
        dif = {d["metrica"]: d for d in r.get("diferencias", [])}
        ben = dif.get("beneficio", {}).get("delta_pct", 0)
        ing = dif.get("ingresos", {}).get("delta_pct", 0)
        return {
            "texto": (f"He simulado el impacto (VIRTUAL, sin tocar datos reales): ingresos "
                      f"{ing:+.1f}%, beneficio {ben:+.1f}%. Confianza {r.get('confianza')}. "
                      "Si quieres, preparo el plan de ejecución para que pase por aprobación."),
            "fuentes": ["Simulador", "Predicción"],
            "visual": {"tipo": "kpis", "items": [
                {"titulo": "Ingresos", "valor": f"{ing:+.1f}%", "riesgo": None},
                {"titulo": "Beneficio", "valor": f"{ben:+.1f}%", "riesgo": None},
                {"titulo": "Riesgo", "valor": (r.get("riesgo") or {}).get("nivel", "BAJO"),
                 "riesgo": (r.get("riesgo") or {}).get("nivel", "BAJO")},
            ]},
        }
    except Exception as e:
        logger.debug("ejecutar_confirmado: %s", e)
        return {"texto": f"He preparado el plan «{cfg['titulo']}»."}
