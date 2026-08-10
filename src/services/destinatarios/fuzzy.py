"""
Coincidencia difusa y normalización para la resolución de destinatarios (Partes E/F/G).

Sin IA y sin dependencias externas: `unicodedata` (quitar acentos) + `difflib` (aproximación).
Permite buscar por nombre/apellido/razón social/CIF/correo/teléfono/alias de forma aproximada
("mercadna"→Mercadona, "jse"→José, "garca"→García) y produce una puntuación de calidad de
coincidencia usada por el orden inteligente del servicio.
"""

import unicodedata
from difflib import SequenceMatcher

# Umbral por debajo del cual una coincidencia difusa se descarta.
UMBRAL_DIFUSO = 0.62


def normalizar(texto) -> str:
    """minúsculas, sin acentos/diacríticos, espacios colapsados."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.lower().split())


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def puntuar(consulta: str, *campos) -> float:
    """Puntúa [0..1] cómo de bien casa `consulta` con cualquiera de `campos`.

    Prioriza (de mayor a menor): igualdad exacta > empieza por > cualquier palabra empieza por >
    subcadena > aproximación difusa (SequenceMatcher) por campo completo o por palabra. Devuelve el
    MEJOR de todos los campos. 0.0 = no casa."""
    q = normalizar(consulta)
    if not q:
        return 0.0
    mejor = 0.0
    for campo in campos:
        c = normalizar(campo)
        if not c:
            continue
        if c == q:
            return 1.0
        if c.startswith(q):
            mejor = max(mejor, 0.94)
            continue
        palabras = c.split()
        if any(p.startswith(q) for p in palabras):
            mejor = max(mejor, 0.86)
            continue
        if q in c:
            mejor = max(mejor, 0.74)
            continue
        # Aproximación difusa: campo completo y mejor palabra individual.
        r = _ratio(q, c)
        r = max(r, max((_ratio(q, p) for p in palabras), default=0.0))
        if r >= UMBRAL_DIFUSO:
            mejor = max(mejor, 0.4 + 0.3 * r)   # difuso siempre por debajo de subcadena
    return mejor


def casa(consulta: str, *campos) -> bool:
    """True si `consulta` casa (exacta, parcial o difusa) con algún campo."""
    return puntuar(consulta, *campos) > 0.0
