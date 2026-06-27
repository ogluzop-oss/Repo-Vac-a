"""
Perfil táctil global (BLOQUE 8 — Fase M).

Define modos de interacción y los tamaños mínimos de control asociados, para que la
UI pueda adaptarse a ratón/teclado, pantallas táctiles, TPV y PDA sin tocar la lógica
de negocio. No fuerza nada por sí solo: expone el perfil activo y helpers que los
widgets/estilos consultan.

Mínimos de accesibilidad táctil: 48 px (recomendado 56 px en TPV). Fuente del perfil:
1) variable de entorno SMART_MANAGER_PERFIL_TACTIL, 2) preferencia de usuario (si se
inyecta con set_perfil), 3) por defecto 'normal'.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

NORMAL = "normal"
TACTIL = "tactil"
TPV = "tpv"
PDA = "pda"

PERFILES = (NORMAL, TACTIL, TPV, PDA)

# Altura mínima de control táctil por perfil (px lógicos).
_ALTURA_MIN = {
    NORMAL: 0,    # sin imposición; respeta el diseño existente
    TACTIL: 48,
    TPV: 56,
    PDA: 44,      # pantallas pequeñas: objetivo táctil mínimo accesible
}

# Espaciado mínimo recomendado entre controles por perfil (px).
_ESPACIADO_MIN = {NORMAL: 6, TACTIL: 10, TPV: 12, PDA: 8}

_perfil_actual: str | None = None


def _normalizar(valor: str | None) -> str | None:
    if not valor:
        return None
    v = str(valor).strip().lower()
    return v if v in PERFILES else None


def perfil_actual() -> str:
    """Perfil táctil activo. Resuelve env → set_perfil → 'normal' (cacheado)."""
    global _perfil_actual
    if _perfil_actual is None:
        _perfil_actual = _normalizar(os.getenv("SMART_MANAGER_PERFIL_TACTIL")) or NORMAL
    return _perfil_actual


def set_perfil(valor: str | None) -> str:
    """Fija el perfil activo (p.ej. desde preferencias de usuario). Devuelve el aplicado."""
    global _perfil_actual
    _perfil_actual = _normalizar(valor) or NORMAL
    logger.info("Perfil táctil establecido: %s", _perfil_actual)
    return _perfil_actual


def es_tactil() -> bool:
    """True si el perfil activo es de interacción táctil (tactil/tpv/pda)."""
    return perfil_actual() in (TACTIL, TPV, PDA)


def altura_min_control() -> int:
    """Altura mínima recomendada para botones/controles en el perfil activo (px)."""
    return _ALTURA_MIN.get(perfil_actual(), 0)


def espaciado_min() -> int:
    """Espaciado mínimo recomendado entre controles en el perfil activo (px)."""
    return _ESPACIADO_MIN.get(perfil_actual(), 6)
