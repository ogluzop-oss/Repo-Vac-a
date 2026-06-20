"""
Cargador de parámetros legales de cotización/IRPF (F4.3.2).

Lee `assets/rrhh/cotizacion_<pais>.json` (fuente única, versionada por ejercicio) y
construye un `ParametrosAnio` que consume el motor de nómina. Patrón idéntico al de
`utils.fiscalidad` (registro JSON editable, sin migraciones). NO accede a BD ni a Qt.
"""

import json
import logging
import os

from src.rrhh.nomina_motor import ParametrosAnio

logger = logging.getLogger("rrhh.parametros_cotizacion")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ruta(pais: str) -> str:
    nombre = f"cotizacion_{pais.lower()}.json"
    try:
        from src.utils import recursos
        return recursos.ruta_recurso("assets", "rrhh", nombre)
    except Exception:
        return os.path.join(_ROOT, "assets", "rrhh", nombre)


def cargar_parametros(anio: int, pais: str = "ES") -> ParametrosAnio:
    """Devuelve los parámetros del ejercicio `anio` (último disponible si no existe el
    exacto). Lanza FileNotFoundError/KeyError si no hay datos para ese país."""
    ruta = _ruta(pais)
    with open(ruta, encoding="utf-8") as f:
        data = json.load(f) or {}
    ejercicios = {k: v for k, v in data.items() if k.isdigit()}
    if not ejercicios:
        raise KeyError(f"Sin ejercicios en {ruta}")
    clave = str(anio) if str(anio) in ejercicios else max(ejercicios, key=int)
    if clave != str(anio):
        logger.info("Cotización %s no encontrada; usando %s", anio, clave)
    return ParametrosAnio.desde_dict(int(clave), pais.upper(), ejercicios[clave])
