"""
Configuracion del motor predictivo (Paquete Enterprise 3, SUBFASE 3.13). Activar/desactivar por
empresa (y opcionalmente tienda) cada dominio predictivo. En proceso; sin tablas nuevas.
"""

FEATURES = ("stock", "ventas", "compras", "tesoreria", "rrhh", "crm", "riesgos", "produccion", "documental")

_DEFAULT = {f: True for f in FEATURES}
_overrides = {}   # {clave_empresa_tienda: {feature: bool}}


def _clave(id_empresa=None, id_tienda=None):
    if not id_empresa:
        try:
            from src.db.empresa import empresa_actual_id
            id_empresa = empresa_actual_id()
        except Exception:
            id_empresa = "_default"
    return f"{id_empresa}:{id_tienda if id_tienda is not None else '*'}"


def activo(feature, id_empresa=None, id_tienda=None) -> bool:
    ov = _overrides.get(_clave(id_empresa, id_tienda), {})
    if feature in ov:
        return bool(ov[feature])
    ov_emp = _overrides.get(_clave(id_empresa, None), {})
    return bool(ov_emp.get(feature, _DEFAULT.get(feature, True)))


def configurar(id_empresa=None, id_tienda=None, **flags) -> dict:
    d = _overrides.setdefault(_clave(id_empresa, id_tienda), {})
    for k, v in flags.items():
        if k in FEATURES:
            d[k] = bool(v)
    return estado(id_empresa, id_tienda)


def estado(id_empresa=None, id_tienda=None) -> dict:
    return {f: activo(f, id_empresa, id_tienda) for f in FEATURES}
