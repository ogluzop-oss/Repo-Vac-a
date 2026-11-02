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
# Gate de TPV PERSISTENTE a nivel de paquete (sobrevive a que el overlay aún no exista): la
# instalación real queda diferida ~400ms tras el arranque (ver `main.py`), así que si el usuario
# entra al TPV antes de que esa instalación llegue a ejecutarse, el `set_tpv_activo` de entonces no
# tendría overlay al que aplicarse — este flag recuerda ese estado para que `instalar_overlay` nazca
# ya con el gate correcto, en vez de mostrarse igualmente la primera vez.
_tpv_abierto = False


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
        if _tpv_abierto:
            _overlay.set_tpv_activo(True)
        # NO `_overlay.show()` incondicional: pasa por el gate único (`_sincronizar_visibilidad`) para
        # que, si la instalación cae mientras el usuario ya está dentro del TPV, SOMA no aparezca igual.
        _overlay._sincronizar_visibilidad()
        logger.info("SOMA overlay instalado (reposo).")
    except Exception as e:
        logger.debug("instalar_overlay: %s", e)
        _overlay = None
    return _overlay


def overlay():
    return _overlay


def set_tpv_activo(activo: bool) -> None:
    """Gate de TPV (petición explícita, para TODOS los roles): úsalo en vez de
    `overlay().set_tpv_activo(...)` — actualiza el flag persistente del paquete (sobrevive a que el
    overlay todavía no se haya instalado, ver `_tpv_abierto` arriba) y, si ya existe, al overlay real."""
    global _tpv_abierto
    _tpv_abierto = bool(activo)
    if _overlay is not None:
        try:
            _overlay.set_tpv_activo(_tpv_abierto)
        except Exception:
            pass


__all__ = ["instalar_overlay", "overlay", "set_tpv_activo"]
