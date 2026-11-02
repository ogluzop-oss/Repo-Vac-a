"""Geo · distancia entre coordenadas (haversine). Motor único, sin dependencias nuevas.

Extraído de `services/crm/rutas.py::_distancia` (antes duplicado ahí) para poder reutilizarlo
en cualquier dominio que necesite ordenar por proximidad geográfica (CRM: clientes; Logística:
almacenes/tiendas). Pura función matemática — no toca la base de datos.
"""

import math

R_TIERRA_KM = 6371.0


def haversine_km(a: tuple, b: tuple) -> float:
    """Distancia aproximada (haversine, km) entre dos puntos ``(lat, lng)``.

    Devuelve ``float('inf')`` si a cualquiera de los dos puntos le falta la latitud o la
    longitud (None) — así el punto sin geolocalizar siempre ordena al final al usarse como
    clave de ``sorted(..., key=...)``, sin necesidad de excluirlo de la lista."""
    if a is None or b is None or None in a or None in b:
        return float("inf")
    R = R_TIERRA_KM
    la1, lo1, la2, lo2 = map(math.radians, [float(a[0]), float(a[1]), float(b[0]), float(b[1])])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))
