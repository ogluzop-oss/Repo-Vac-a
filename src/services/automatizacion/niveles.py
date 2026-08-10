"""
Niveles de automatizacion (Paquete Enterprise 4, SUBFASE 4.8).

  informar  → solo avisa (Centro/notificacion), no actua.
  proponer  → prepara una propuesta (sin ejecutar acciones criticas).
  aprobar   → lanza el Workflow/BPM de aprobacion existente.
  auto      → ejecuta la accion automaticamente (SOLO si esta configurado; nunca acciones
              criticas sin autorizacion explicita).
"""

INFORMAR = "informar"
PROPONER = "proponer"
APROBAR = "aprobar"
AUTO = "auto"

TODOS = [INFORMAR, PROPONER, APROBAR, AUTO]

# Acciones que NUNCA se ejecutan en modo AUTO sin autorizacion explicita.
CRITICAS = {"crear_pedido", "enviar_correo", "crear_factura"}

# Estado resultante en el log de ejecuciones segun el nivel.
ESTADO_POR_NIVEL = {INFORMAR: "INFORMADA", PROPONER: "PROPUESTA",
                    APROBAR: "PENDIENTE", AUTO: "EJECUTADA"}


def normalizar(nivel) -> str:
    n = str(nivel or PROPONER).lower()
    return n if n in TODOS else PROPONER


def permite_ejecutar(nivel, accion, *, auto_critico=False) -> bool:
    """True si el nivel implica EJECUTAR la accion ahora (auto), con guarda de criticidad."""
    if nivel != AUTO:
        return False
    if accion in CRITICAS and not auto_critico:
        return False
    return True
