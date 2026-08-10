"""
Global SaaS · Global Configuration Service (Fase VI · Bloque 13). Configuración global de la
plataforma: variables globales, branding, idiomas, zonas horarias y formatos regionales. Reutiliza
la i18n y el branding SaaS existentes; expone valores por región. Sin BD propia (config en memoria +
reutilización de servicios existentes).
"""

from __future__ import annotations

# Variables globales de plataforma (en memoria; preparado para respaldo persistente).
_VARIABLES = {
    "plataforma": "Smart Manager AI",
    "modelo_despliegue": "cloud",
    "region_por_defecto": "eu",
}

# Formatos regionales por región (fecha/decimal/moneda por defecto).
FORMATOS_REGION = {
    "eu": {"fecha": "%d/%m/%Y", "decimal": ",", "moneda": "EUR", "tz": "Europe/Madrid"},
    "am": {"fecha": "%m/%d/%Y", "decimal": ".", "moneda": "USD", "tz": "America/New_York"},
    "as": {"fecha": "%Y-%m-%d", "decimal": ".", "moneda": "CNY", "tz": "Asia/Shanghai"},
    "af": {"fecha": "%d/%m/%Y", "decimal": ".", "moneda": "ZAR", "tz": "Africa/Johannesburg"},
    "oc": {"fecha": "%d/%m/%Y", "decimal": ".", "moneda": "AUD", "tz": "Australia/Sydney"},
}


def get(clave, por_defecto=None):
    return _VARIABLES.get(clave, por_defecto)


def set(clave, valor):
    _VARIABLES[clave] = valor
    return True


def idiomas() -> list:
    """Idiomas soportados (reutiliza la i18n existente, 20 idiomas)."""
    try:
        from src.utils import i18n
        return list(i18n.LANGUAGES.keys())
    except Exception:
        return ["es", "en"]


def branding(id_empresa=None) -> dict:
    """Branding de una empresa (reutiliza el branding SaaS existente; degradable)."""
    try:
        from src.services.saas import branding as _b
        if hasattr(_b, "obtener"):
            return _b.obtener(id_empresa) or {}
    except Exception:
        pass
    return {}


def formato_region(region="eu") -> dict:
    return dict(FORMATOS_REGION.get(region, FORMATOS_REGION["eu"]))


def descriptor() -> dict:
    return {"variables": dict(_VARIABLES), "idiomas": idiomas(),
            "regiones_formato": list(FORMATOS_REGION.keys())}


__all__ = ["FORMATOS_REGION", "get", "set", "idiomas", "branding", "formato_region", "descriptor"]
