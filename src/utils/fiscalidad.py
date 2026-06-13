"""
Sistema fiscal de Smart Manager AI: IVA por PAÍS (independiente de la divisa).

El país fiscal de la empresa (CONFIGURACIÓN → DATOS DE EMPRESA) determina
AUTOMÁTICAMENTE el tipo de IVA usado en toda la documentación (tickets,
facturas, devoluciones, informes). NO modifica precios (los PVP ya incluyen IVA)
ni la gestión de divisas (que se configura aparte, en GESTIÓN CAJA).

Fuente única y editable: ``assets/fiscalidad/iva_paises.json`` (país → divisa,
IVA principal, fecha de actualización). Para actualizar un tipo por un cambio
legal, basta editar el JSON; no hay valores fiscales repartidos por el código.

Arquitectura preparada para futuras ampliaciones (varios tipos por país,
asignación por artículo/categoría) sin rediseñar el sistema. Multiempresa:
el país fiscal depende de ``id_empresa`` (nunca global).
"""

import json
import logging
import os

logger = logging.getLogger("fiscalidad")

_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_THIS))
_DEFECTO_PAIS = "ES"
_IVA_DEFECTO = 21.0

_registro_cache = None


def _ruta_registro():
    try:
        from src.utils import recursos
        return recursos.ruta_recurso("assets", "fiscalidad", "iva_paises.json")
    except Exception:
        return os.path.join(_ROOT, "assets", "fiscalidad", "iva_paises.json")


def _registro() -> dict:
    global _registro_cache
    if _registro_cache is not None:
        return _registro_cache
    data = {}
    try:
        with open(_ruta_registro(), encoding="utf-8") as f:
            data = (json.load(f) or {}).get("paises", {})
    except Exception as e:
        logger.error("No se pudo leer el registro fiscal de IVA: %s", e)
    _registro_cache = data
    return data


def recargar():
    """Olvida la caché del registro (releer la próxima vez)."""
    global _registro_cache
    _registro_cache = None


def info_pais(code=None) -> dict:
    """Metadatos fiscales del país: {code, nombre, divisa, iva, actualizado}."""
    code = (code or _DEFECTO_PAIS).upper()
    reg = _registro()
    d = reg.get(code) or reg.get(_DEFECTO_PAIS) or {}
    return {
        "code": code if code in reg else _DEFECTO_PAIS,
        "nombre": d.get("nombre", code),
        "divisa": d.get("divisa", "EUR"),
        "iva": float(d.get("iva", _IVA_DEFECTO)),
        "actualizado": d.get("actualizado", ""),
    }


def iva_de_pais(code=None) -> float:
    """Tipo de IVA principal (%) del país indicado."""
    return info_pais(code)["iva"]


def nombre_pais(code=None) -> str:
    return info_pais(code)["nombre"]


def paises_disponibles() -> list[dict]:
    """Países compatibles con las divisas que soporta la app, ordenados por
    nombre. Cada item: {code, nombre, divisa, iva}. Si no se puede consultar la
    lista de divisas, se devuelven todos los países del registro."""
    try:
        from src.utils import divisas
        soportadas = set(divisas.monedas_soportadas())
    except Exception:
        soportadas = None
    out = []
    for code, d in _registro().items():
        if soportadas is None or d.get("divisa") in soportadas:
            out.append({"code": code, "nombre": d.get("nombre", code),
                        "divisa": d.get("divisa", ""), "iva": float(d.get("iva", _IVA_DEFECTO))})
    out.sort(key=lambda x: x["nombre"])
    return out


def pais_fiscal_empresa(id_empresa=None) -> str:
    """Código del país fiscal de la empresa (por defecto ES)."""
    try:
        from src.db.empresa import obtener_empresa
        emp = obtener_empresa(id_empresa) or {}
        return (emp.get("pais_fiscal") or _DEFECTO_PAIS).upper()
    except Exception:
        return _DEFECTO_PAIS


def iva_empresa(id_empresa=None) -> float:
    """Tipo de IVA (%) que corresponde a la empresa según su país fiscal."""
    return iva_de_pais(pais_fiscal_empresa(id_empresa))
