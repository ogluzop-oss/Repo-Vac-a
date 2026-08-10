"""
Registro de adaptadores de banca. `obtener_adaptador(proveedor)` resuelve por código; los proveedores sin
adaptador propio caen al PSD2 genérico (honesto: funciona con cualquier agregador que respete Berlin Group).
"""

from src.services.banca_online.proveedores.psd2_generico import AdaptadorPSD2

_ADAPTADORES = {a.codigo: a for a in (AdaptadorPSD2(),)}
_GENERICO = _ADAPTADORES["psd2_generico"]


def obtener_adaptador(proveedor):
    return _ADAPTADORES.get((proveedor or "").lower(), _GENERICO)


def proveedores_con_adaptador():
    return sorted(_ADAPTADORES.keys())
