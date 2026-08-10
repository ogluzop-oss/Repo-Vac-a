"""
Cache TTL en proceso para la IA (SUBFASE 10 soporte). Evita recomputar analisis costosos en
peticiones seguidas. No persiste nada; RAM efimera por proceso.
"""

import time

_C = {}   # clave -> (expira_ts, valor)


def get(clave):
    v = _C.get(clave)
    if not v:
        return None
    if v[0] < time.time():
        _C.pop(clave, None)
        return None
    return v[1]


def set(clave, valor, ttl=60):
    _C[clave] = (time.time() + ttl, valor)
    return valor


def memoizar(clave, fn, ttl=60):
    v = get(clave)
    if v is not None:
        return v
    return set(clave, fn(), ttl)


def limpiar():
    _C.clear()
