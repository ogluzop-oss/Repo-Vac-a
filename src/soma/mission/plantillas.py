"""
Plantillas de MISIÓN (Fase 6): descomposición automática de un objetivo en tareas con dependencias y
especialistas. Cada tarea se asigna a un dominio de Especialista IA (AgentManager) o a un tipo
especial (simulación, predicción, aprobación) que el motor resuelve reutilizando el servicio adecuado.
Las tareas independientes se ejecutan en PARALELO; las dependientes esperan a sus predecesoras.
"""

from src.soma.mission.modelo import Mision, Tarea

# Dominios "especiales" que el motor resuelve con un servicio concreto (no un agente):
#   simulacion → Simulador ; prediccion → PredictionService ; gemelo → Gemelo ;
#   aprobacion → Autonomía/Workflow/Gobierno (acción crítica: NUNCA ejecuta directa)


def _abrir_tienda(m: Mision):
    m.tareas = [
        Tarea("fin", "Análisis financiero", dominio="financiero", eta_min=2),
        Tarea("pred", "Predicción de ventas", dominio="prediccion", eta_min=2),
        Tarea("stock", "Necesidades de stock", dominio="stock", eta_min=2),
        Tarea("rrhh", "Necesidades de personal", dominio="rrhh", eta_min=2),
        Tarea("sim", "Simulación económica", dominio="simulacion", deps=["fin", "pred"], eta_min=3),
        Tarea("wf", "Workflow documental y solicitud de aprobación", dominio="aprobacion",
              deps=["sim", "stock", "rrhh"], eta_min=1, critica=True),
    ]
    m._sim_vars = [{"variable": "tiendas", "valor": 1}]
    return m


def _mejorar_ventas(m: Mision):
    m.tareas = [
        Tarea("com", "Análisis comercial y clientes", dominio="comercial", eta_min=2),
        Tarea("pred", "Detección de oportunidades", dominio="prediccion", eta_min=2),
        Tarea("sim", "Simulación de campaña", dominio="simulacion", deps=["com", "pred"], eta_min=3),
        Tarea("prop", "Propuesta y solicitud de aprobación", dominio="aprobacion", deps=["sim"],
              eta_min=1, critica=True),
    ]
    m._sim_vars = [{"variable": "promocion", "valor": 10}]
    return m


def _reducir_costes(m: Mision):
    m.tareas = [
        Tarea("bi", "Revisión de gastos y márgenes", dominio="financiero", eta_min=2),
        Tarea("comp", "Comparativa de proveedores", dominio="compras", eta_min=2),
        Tarea("sim", "Simulación de ajuste de costes", dominio="simulacion", deps=["bi", "comp"],
              eta_min=3),
        Tarea("prop", "Propuesta y solicitud de aprobación", dominio="aprobacion", deps=["sim"],
              eta_min=1, critica=True),
    ]
    m._sim_vars = [{"variable": "proveedor", "valor": -10}]
    return m


CATALOGO = {
    "abrir_tienda": {"titulo": "Abrir una nueva tienda",
                     "claves": (("abrir", "tienda"), ("nueva", "tienda"), ("montar", "tienda")),
                     "construir": _abrir_tienda},
    "mejorar_ventas": {"titulo": "Mejorar las ventas",
                       "claves": (("mejorar", "ventas"), ("subir", "ventas"), ("aumentar", "ventas")),
                       "construir": _mejorar_ventas},
    "reducir_costes": {"titulo": "Reducir costes",
                       "claves": (("reducir", "costes"), ("bajar", "costes"), ("ahorrar",)),
                       "construir": _reducir_costes},
}


def detectar(texto):
    """Devuelve la clave de plantilla si el objetivo corresponde a una misión conocida; None si no."""
    t = (texto or "").lower()
    for clave, cfg in CATALOGO.items():
        for grupo in cfg["claves"]:
            if all(k in t for k in grupo):
                return clave
    return None


def construir(clave, objetivo, *, usuario=None, id_empresa=None, prioridad="NORMAL") -> Mision:
    cfg = CATALOGO.get(clave)
    m = Mision(objetivo, plantilla=clave, prioridad=prioridad, usuario=usuario, id_empresa=id_empresa)
    if cfg:
        cfg["construir"](m)
    return m
