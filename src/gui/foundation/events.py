"""
Event Registry de la UI Enterprise (Foundation). Todos los `EnterprisePanel` publican eventos
ESTÁNDAR de interfaz en el Event Bus existente, de forma que el Copiloto IA, el Centro de Actividad
y el propio Event Bus hablen el mismo idioma.

RESTRICCIÓN (regla de arquitectura): SOLO eventos de INTERFAZ — observacionales, idempotentes y sin
lógica de negocio. Queda PROHIBIDO publicar aquí eventos de dominio (CrearFactura, EliminarPedido,
RegistrarVenta, CerrarCaja…): eso pertenece a la capa de servicios. Así el Event Bus se mantiene
limpio. La publicación es best-effort (bulletproof): nunca rompe la UI.
"""

import logging

logger = logging.getLogger("gui.foundation.events")

# Catálogo cerrado de eventos de UI permitidos.
PANEL_OPENED = "UI_PANEL_OPENED"
PANEL_CLOSED = "UI_PANEL_CLOSED"
DATA_LOADED = "UI_DATA_LOADED"
ACTION_EXECUTED = "UI_ACTION_EXECUTED"
REFRESH_REQUESTED = "UI_REFRESH_REQUESTED"
PERMISSION_CHANGED = "UI_PERMISSION_CHANGED"

_PERMITIDOS = frozenset({PANEL_OPENED, PANEL_CLOSED, DATA_LOADED, ACTION_EXECUTED,
                         REFRESH_REQUESTED, PERMISSION_CHANGED})


def publicar_ui(evento, *, panel=None, usuario=None, id_empresa=None, datos=None) -> None:
    """Publica un evento de UI en el Event Bus (observacional). Ignora eventos no-UI (protección
    contra fugas de dominio) y cualquier fallo."""
    if evento not in _PERMITIDOS:
        logger.debug("evento de UI no permitido, ignorado: %s", evento)
        return
    try:
        from src.services import eventos as EV
        EV.publicar(evento, id_empresa=id_empresa, origen="ui", ref_entidad="panel",
                    ref_id=str(panel) if panel else None, usuario=usuario,
                    payload={"panel": panel, **(datos or {})})
    except Exception as e:
        logger.debug("publicar_ui(%s): %s", evento, e)
