"""
gui/soma — Experiencia visual de SOMA (Fase 2): Character Pack, personaje, animaciones/
microanimaciones, overlay (reposo/activo) y panel conversacional. SOLO presentación: refleja el
estado del SomaKernel (única fuente de verdad); nunca decide estados ni contiene lógica de negocio.

Punto de entrada:
    from src.gui.soma import instalar_overlay
    instalar_overlay(app)   # crea el overlay una vez y lo conecta al kernel
"""

import logging

logger = logging.getLogger("gui.soma")

_overlay = None


def instalar_overlay(app):
    """Crea el SomaOverlay UNA sola vez por sesión, lo acopla a `app` (SmartManagerApp) y lo conecta
    al SomaKernel. Idempotente y a prueba de fallos (nunca rompe el ERP)."""
    global _overlay
    if _overlay is not None:
        # Re-login: el overlay (singleton) ya existe pero pudo quedar oculto por el gate de sesión al
        # cerrar la sesión anterior. Reactiva la sesión para que vuelva a mostrarse tras iniciar sesión.
        try:
            _overlay.set_sesion_activa(True)
        except Exception:
            pass
        return _overlay
    try:
        from src.gui.soma.overlay import SomaOverlay
        from src.soma import kernel as _k
        _overlay = SomaOverlay(app)
        _overlay.conectar_kernel(_k())
        _overlay.show()
        _overlay.raise_()
        logger.info("SOMA overlay instalado (reposo).")
    except Exception as e:
        logger.debug("instalar_overlay: %s", e)
        _overlay = None
    return _overlay


def overlay():
    return _overlay


__all__ = ["instalar_overlay", "overlay"]
