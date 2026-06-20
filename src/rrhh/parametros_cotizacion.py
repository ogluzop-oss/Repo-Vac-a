"""
Cargador de parámetros legales de cotización/IRPF (F4.3.2 + endurecido en F4.6).

Lee `assets/rrhh/cotizacion_<pais>.json` (fuente única, versionada por ejercicio) y
construye un `ParametrosAnio` que consume el motor de nómina. Patrón idéntico al de
`utils.fiscalidad` (registro JSON editable, sin migraciones). NO accede a BD ni a Qt.

F4.6: carga robusta (JSON corrupto / fichero ausente / año inexistente con fallback al
último disponible) + validación de integridad (claves/contingencias/bases/grupos/tipos).
Ante datos incompletos lanza `ParametrosCotizacionError` (no produce importes corruptos
en silencio). El selector automático `parametros[año]` se mantiene sin cambios.
"""

import json
import logging
import os

from src.rrhh.nomina_motor import ParametrosAnio

logger = logging.getLogger("rrhh.parametros_cotizacion")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ParametrosCotizacionError(Exception):
    """Recurso de cotización ausente, corrupto o incompleto."""


# Claves obligatorias y sus contingencias mínimas (validación de integridad).
_SS_TRAB = ("comunes", "fp", "mei")
_SS_EMP = ("comunes", "fp", "fogasa", "at_ep", "mei")
_DESEMPLEO = ("indefinido", "temporal")
_BASES = ("tope_max_mensual", "tope_min_mensual")


def _ruta(pais: str) -> str:
    nombre = f"cotizacion_{pais.lower()}.json"
    try:
        from src.utils import recursos
        return recursos.ruta_recurso("assets", "rrhh", nombre)
    except Exception:
        return os.path.join(_ROOT, "assets", "rrhh", nombre)


def _num(d, clave, contexto):
    v = d.get(clave)
    if not isinstance(v, (int, float)):
        raise ParametrosCotizacionError(
            f"Parámetro '{clave}' ausente o no numérico en {contexto}.")
    return float(v)


def _validar(ej: dict, clave: str):
    """Valida la estructura de un ejercicio. Lanza ParametrosCotizacionError si falta
    cualquier bloque/contingencia/base o hay tipos incorrectos."""
    ctx = f"ejercicio {clave}"
    for bloque, req in (("ss_trabajador", _SS_TRAB), ("ss_empresa", _SS_EMP),
                        ("desempleo_trabajador", _DESEMPLEO), ("desempleo_empresa", _DESEMPLEO)):
        sub = ej.get(bloque)
        if not isinstance(sub, dict):
            raise ParametrosCotizacionError(f"Falta el bloque '{bloque}' en {ctx}.")
        for k in req:
            _num(sub, k, f"{bloque} ({ctx})")
    bases = ej.get("bases")
    if not isinstance(bases, dict):
        raise ParametrosCotizacionError(f"Falta el bloque 'bases' en {ctx}.")
    for k in _BASES:
        _num(bases, k, f"bases ({ctx})")
    grupos = ej.get("grupos")
    if not isinstance(grupos, dict) or not grupos:
        raise ParametrosCotizacionError(f"Faltan 'grupos' de cotización en {ctx}.")
    for g, lim in grupos.items():
        if not isinstance(lim, dict) or "min" not in lim or "max" not in lim:
            raise ParametrosCotizacionError(f"Grupo '{g}' sin min/max en {ctx}.")
        _num(lim, "min", f"grupo {g} ({ctx})")
        _num(lim, "max", f"grupo {g} ({ctx})")


def cargar_parametros(anio: int, pais: str = "ES") -> ParametrosAnio:
    """Devuelve los parámetros del ejercicio `anio` (último disponible si no existe el
    exacto). Carga robusta + validación de integridad."""
    ruta = _ruta(pais)
    if not os.path.exists(ruta):
        raise ParametrosCotizacionError(f"Recurso de cotización no encontrado: {ruta}")
    try:
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ParametrosCotizacionError(f"Recurso de cotización corrupto ({ruta}): {e}") from e
    if not isinstance(data, dict):
        raise ParametrosCotizacionError(f"Recurso de cotización con formato inválido: {ruta}")
    ejercicios = {k: v for k, v in data.items() if k.isdigit() and isinstance(v, dict)}
    if not ejercicios:
        raise ParametrosCotizacionError(f"Sin ejercicios válidos en {ruta}")
    clave = str(anio) if str(anio) in ejercicios else max(ejercicios, key=int)
    if clave != str(anio):
        logger.info("Cotización %s no encontrada; usando %s (último disponible).", anio, clave)
    _validar(ejercicios[clave], clave)
    return ParametrosAnio.desde_dict(int(clave), pais.upper(), ejercicios[clave])
