"""
Registro de proveedores fiscales por territorio — añadir un régimen nuevo
(Verifactu, Facturae, TicketBAI, otros países) NO requiere tocar el núcleo.

Mismo patrón que `pagos`/`webhooks`/`ecommerce`: decorador `@registrar_proveedor`
+ descubrimiento automático (con lista explícita `MODULOS` robusta en el .exe).
"""

import importlib
import logging
import pkgutil

logger = logging.getLogger("fiscal.registry")

_REGISTRO = {}          # nombre -> {"clase", "territorios"}
_descubierto = False


def registrar_proveedor(nombre, territorios=()):
    def deco(clase):
        clase.nombre = nombre
        clase.territorios = tuple(territorios)
        _REGISTRO[nombre] = {"clase": clase, "territorios": tuple(territorios)}
        return clase
    return deco


def _descubrir():
    global _descubierto
    if _descubierto:
        return
    _descubierto = True
    try:
        import src.services.fiscal as paquete
    except Exception as e:
        logger.error("No se pudo cargar el paquete fiscal: %s", e)
        return
    nombres = set(getattr(paquete, "MODULOS", []) or [])
    try:
        for _f, modname, _p in pkgutil.iter_modules(paquete.__path__):
            nombres.add(modname)
    except Exception:
        pass
    for modname in nombres:
        if modname in ("registry", "factory", "base", "__init__"):
            continue
        try:
            importlib.import_module(f"src.services.fiscal.{modname}")
        except Exception as e:
            logger.warning("Proveedor fiscal '%s' no se pudo cargar: %s", modname, e)


def clase_de(nombre):
    _descubrir()
    e = _REGISTRO.get(nombre)
    return e["clase"] if e else None


def proveedores_registrados() -> dict:
    _descubrir()
    return {k: v["territorios"] for k, v in _REGISTRO.items()}


def proveedor_para_territorio(territorio):
    """Primer proveedor que cubre el territorio (o None)."""
    _descubrir()
    for nombre, e in _REGISTRO.items():
        if territorio in e["territorios"]:
            return e["clase"]
    return None
