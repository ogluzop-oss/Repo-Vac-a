"""
Registro de pasarelas de pago — permite añadir nuevas pasarelas SIN tocar el
núcleo de la aplicación.

Cada adaptador se registra con el decorador ``@registrar(...)`` en su propio
módulo. El registro descubre automáticamente todos los módulos del paquete
``src.services.tpv.pagos`` (basta con soltar un fichero nuevo), de modo que ni el
factory, ni la UI, ni la BD necesitan modificarse para soportar un proveedor más.

Ejemplo para una pasarela nueva (fichero ``bizum.py``):

    from src.services.tpv.pagos.base import PasarelaPago
    from src.services.tpv.pagos.registry import registrar

    @registrar("bizum", "Bizum", orden=40)
    class PasarelaBizum(PasarelaPago):
        ...
"""

import importlib
import logging
import pkgutil

logger = logging.getLogger("pagos.registry")

# nombre -> {"clase", "etiqueta", "recomendada", "orden"}
_REGISTRO: dict = {}
_descubierto = False


def registrar(nombre: str, etiqueta: str = None, recomendada: bool = False, orden: int = 100):
    """Decorador que da de alta una pasarela en el registro."""
    def deco(clase):
        clase.nombre = nombre
        _REGISTRO[nombre] = {"clase": clase, "etiqueta": etiqueta or nombre.capitalize(),
                             "recomendada": recomendada, "orden": orden}
        return clase
    return deco


def _descubrir():
    """Importa todos los módulos del paquete de pagos para ejecutar sus registros."""
    global _descubierto
    if _descubierto:
        return
    _descubierto = True
    try:
        import src.services.tpv.pagos as paquete
    except Exception as e:
        logger.error("No se pudo cargar el paquete de pagos: %s", e)
        return
    for _f, modname, _p in pkgutil.iter_modules(paquete.__path__):
        if modname in ("registry", "factory", "base", "__init__"):
            continue
        try:
            importlib.import_module(f"src.services.tpv.pagos.{modname}")
        except Exception as e:
            logger.warning("Pasarela '%s' no se pudo cargar: %s", modname, e)


def pasarelas_registradas() -> dict:
    """Pasarelas registradas, ordenadas (recomendada primero, luego por 'orden')."""
    _descubrir()
    return dict(sorted(_REGISTRO.items(),
                       key=lambda kv: (not kv[1]["recomendada"], kv[1]["orden"], kv[0])))


def clase_de(nombre: str):
    """Clase de pasarela por nombre, o None si no está registrada."""
    _descubrir()
    e = _REGISTRO.get(nombre)
    return e["clase"] if e else None


def proveedor_por_defecto() -> str:
    """Nombre de la pasarela recomendada (o la primera registrada / 'simulado')."""
    _descubrir()
    for n, e in pasarelas_registradas().items():
        if e["recomendada"]:
            return n
    return next(iter(_REGISTRO), "simulado")
