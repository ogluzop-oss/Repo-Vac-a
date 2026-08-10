"""
Configuracion global de automatizacion por empresa (Paquete Enterprise 4). El detalle por regla
(activa/nivel/version) vive en automatizaciones_reglas; aqui solo el interruptor global y el
permiso para ejecutar acciones CRITICAS en modo auto (por defecto NO).
"""

_habilitado = {}       # id_empresa -> bool
_auto_critico = {}     # id_empresa -> bool


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return "_default"


def activo(id_empresa=None) -> bool:
    return _habilitado.get(_emp(id_empresa), True)


def activar(id_empresa=None, on=True) -> None:
    _habilitado[_emp(id_empresa)] = bool(on)


def auto_critico_permitido(id_empresa=None) -> bool:
    return _auto_critico.get(_emp(id_empresa), False)


def set_auto_critico(id_empresa=None, on=False) -> None:
    _auto_critico[_emp(id_empresa)] = bool(on)
