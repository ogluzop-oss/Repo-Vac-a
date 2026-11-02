"""Geo · geocodificación aproximada de códigos postales ESPAÑOLES, por PROVINCIA.

Honestidad de capacidad (mismo criterio que "Honestidad IA/ML" en CLAUDE.md — nunca fingir más
precisión de la que hay): España codifica la provincia en los 2 primeros dígitos del código postal
(01–52, mapeo oficial y estable — Correos/INE). Este módulo NO geocodifica una dirección exacta:
devuelve las coordenadas de la CAPITAL de la provincia correspondiente, como aproximación de
proximidad (decenas de km de margen dentro de la provincia). Es intencionadamente así — sin llamada
de red ni servicio externo, geocodifica en el momento de guardar el centro (una sola vez, ver
`db/centros.py`) y basta para ordenar almacenes/centros por proximidad aproximada
(`services/tpv/online_orders_service.py::buscar_almacenes_con_stock`). Si en el futuro se necesita
precisión de dirección exacta, esto se sustituiría por un servicio de geocodificación real (API
externa) — no está hecho ahora, y no se debe fingir que lo está.

Fuente de las coordenadas: ubicación real y conocida del ayuntamiento/centro de cada capital de
provincia (las 50 provincias + Ceuta y Melilla, códigos 01-52).
"""

from __future__ import annotations

import re

# Prefijo de 2 dígitos del CP -> (latitud, longitud) de la CAPITAL de esa provincia.
_CAPITALES_PROVINCIA: dict[str, tuple[float, float]] = {
    "01": (42.8467, -2.6716),   # Álava (Vitoria-Gasteiz)
    "02": (38.9943, -1.8585),   # Albacete
    "03": (38.3452, -0.4810),   # Alicante
    "04": (36.8381, -2.4597),   # Almería
    "05": (40.6566, -4.6818),   # Ávila
    "06": (38.8794, -6.9707),   # Badajoz
    "07": (39.5696, 2.6502),    # Illes Balears (Palma)
    "08": (41.3851, 2.1734),    # Barcelona
    "09": (42.3439, -3.6969),   # Burgos
    "10": (39.4753, -6.3724),   # Cáceres
    "11": (36.5271, -6.2886),   # Cádiz
    "12": (39.9864, -0.0513),   # Castellón de la Plana
    "13": (38.9848, -3.9272),   # Ciudad Real
    "14": (37.8882, -4.7794),   # Córdoba
    "15": (43.3623, -8.4115),   # A Coruña
    "16": (40.0704, -2.1374),   # Cuenca
    "17": (41.9794, 2.8214),    # Girona
    "18": (37.1773, -3.5986),   # Granada
    "19": (40.6333, -3.1669),   # Guadalajara
    "20": (43.3183, -1.9812),   # Gipuzkoa (Donostia-San Sebastián)
    "21": (37.2614, -6.9447),   # Huelva
    "22": (42.1401, -0.4089),   # Huesca
    "23": (37.7796, -3.7849),   # Jaén
    "24": (42.5987, -5.5671),   # León
    "25": (41.6176, 0.6200),    # Lleida
    "26": (42.4627, -2.4449),   # La Rioja (Logroño)
    "27": (43.0121, -7.5560),   # Lugo
    "28": (40.4168, -3.7038),   # Madrid
    "29": (36.7213, -4.4213),   # Málaga
    "30": (37.9922, -1.1307),   # Murcia
    "31": (42.8125, -1.6458),   # Navarra (Pamplona)
    "32": (42.3358, -7.8639),   # Ourense
    "33": (43.3603, -5.8448),   # Asturias (Oviedo)
    "34": (42.0096, -4.5288),   # Palencia
    "35": (28.1235, -15.4363),  # Las Palmas (Las Palmas de Gran Canaria)
    "36": (42.4310, -8.6444),   # Pontevedra
    "37": (40.9701, -5.6635),   # Salamanca
    "38": (28.4636, -16.2518),  # Santa Cruz de Tenerife
    "39": (43.4623, -3.8099),   # Cantabria (Santander)
    "40": (40.9429, -4.1088),   # Segovia
    "41": (37.3891, -5.9845),   # Sevilla
    "42": (41.7636, -2.4649),   # Soria
    "43": (41.1189, 1.2445),    # Tarragona
    "44": (40.3456, -1.1065),   # Teruel
    "45": (39.8628, -4.0273),   # Toledo
    "46": (39.4699, -0.3763),   # Valencia
    "47": (41.6523, -4.7245),   # Valladolid
    "48": (43.2630, -2.9350),   # Bizkaia (Bilbao)
    "49": (41.5033, -5.7446),   # Zamora
    "50": (41.6488, -0.8891),   # Zaragoza
    "51": (35.8894, -5.3213),   # Ceuta
    "52": (35.2923, -2.9381),   # Melilla
}

_CP_RE = re.compile(r"^\d{5}$")


def geocodificar_cp(cp: str) -> tuple[float, float] | None:
    """Aproxima la ubicación (latitud, longitud) de un código postal ESPAÑOL a partir de su
    prefijo de provincia (2 primeros dígitos). PRECISIÓN DE PROVINCIA, no de dirección exacta
    (ver docstring del módulo) — devuelve las coordenadas de la capital de provincia.

    Devuelve ``None`` si `cp` no es un CP español válido (5 dígitos) o el prefijo no corresponde
    a ninguna provincia conocida (01-52) — nunca inventa una coordenada."""
    if not cp:
        return None
    cp = str(cp).strip()
    if not _CP_RE.match(cp):
        return None
    prefijo = cp[:2]
    return _CAPITALES_PROVINCIA.get(prefijo)
