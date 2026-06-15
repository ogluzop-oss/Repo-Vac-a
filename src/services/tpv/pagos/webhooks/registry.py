"""
Registro de verificadores de webhook — añadir un proveedor nuevo NO requiere
tocar el núcleo (mismo patrón que el registro de pasarelas).

Cada verificador se registra con ``@registrar_webhook("nombre")`` en su módulo;
el registro descubre automáticamente los módulos del paquete ``webhooks``.
"""

import importlib
import logging
import pkgutil

logger = logging.getLogger("pagos.webhooks.registry")

_REGISTRO: dict = {}
_descubierto = False


def registrar_webhook(nombre: str):
    def deco(clase):
        clase.nombre = nombre
        _REGISTRO[nombre] = clase
        return clase
    return deco


def _descubrir():
    global _descubierto
    if _descubierto:
        return
    _descubierto = True
    try:
        import src.services.tpv.pagos.webhooks as paquete
    except Exception as e:
        logger.error("No se pudo cargar el paquete de webhooks: %s", e)
        return
    for _f, modname, _p in pkgutil.iter_modules(paquete.__path__):
        if modname in ("registry", "handler", "base", "__init__"):
            continue
        try:
            importlib.import_module(f"src.services.tpv.pagos.webhooks.{modname}")
        except Exception as e:
            logger.warning("Verificador webhook '%s' no se pudo cargar: %s", modname, e)


def verificador_de(proveedor: str):
    """Instancia del verificador del proveedor, o None si no está registrado."""
    _descubrir()
    clase = _REGISTRO.get(proveedor)
    return clase() if clase else None


def verificadores_registrados() -> list:
    _descubrir()
    return sorted(_REGISTRO.keys())
