"""
Registro de adaptadores de proveedor ESL. `obtener_adaptador(proveedor)` resuelve por código; los
proveedores sin adaptador específico (solum/pricer/hanshow por ahora) caen al REST genérico —honesto:
funciona con su API si respeta el formato neutro, y se sustituye por un adaptador propio cuando se
implemente, sin tocar el resto del sistema.
"""

from src.services.esl.proveedores.imagotag import AdaptadorImagotag
from src.services.esl.proveedores.rest_generico import AdaptadorRestGenerico

_ADAPTADORES = {a.codigo: a for a in (AdaptadorImagotag(), AdaptadorRestGenerico())}
_GENERICO = _ADAPTADORES["rest_generico"]


def obtener_adaptador(proveedor):
    return _ADAPTADORES.get((proveedor or "").lower(), _GENERICO)


def proveedores_con_adaptador():
    return sorted(_ADAPTADORES.keys())
