"""
Configuracion de la IA por empresa (SUBFASE 11). Permite activar/desactivar cada capacidad
(resumenes, anomalias, recomendaciones, predicciones, consultas, analisis) y ajustar umbrales.

NO crea tablas: se mantiene en proceso con valores por defecto sensatos + overrides en runtime
(SaaS-ready). Nada sensible se persiste fuera de la BD existente.
"""

FEATURES = ("resumenes", "anomalias", "recomendaciones", "predicciones", "consultas", "analisis")

_DEFAULT = {f: True for f in FEATURES}
# Umbrales por defecto de deteccion de anomalias (configurables, sin alarmas agresivas).
_UMBRALES = {
    "desviacion_ventas_pct": 40,     # % de desviacion vs media historica
    "merma_pct": 5,                  # % de merma sobre stock
    "devoluciones_pct": 15,          # % devoluciones sobre ventas
    "sync_errores": 1,               # nº de errores de sync para alertar
}

_overrides = {}   # {id_empresa: {feature: bool}}
_umbral_ov = {}   # {id_empresa: {umbral: valor}}


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return "_default"


def activo(feature, id_empresa=None) -> bool:
    ov = _overrides.get(_emp(id_empresa), {})
    return bool(ov.get(feature, _DEFAULT.get(feature, True)))


def configurar(id_empresa=None, **flags) -> dict:
    emp = _emp(id_empresa)
    d = _overrides.setdefault(emp, {})
    for k, v in flags.items():
        if k in FEATURES:
            d[k] = bool(v)
    return estado(emp)


def estado(id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    ov = _overrides.get(emp, {})
    return {f: bool(ov.get(f, _DEFAULT[f])) for f in FEATURES}


def umbral(clave, id_empresa=None):
    return _umbral_ov.get(_emp(id_empresa), {}).get(clave, _UMBRALES.get(clave))


def set_umbral(clave, valor, id_empresa=None):
    _umbral_ov.setdefault(_emp(id_empresa), {})[clave] = valor
