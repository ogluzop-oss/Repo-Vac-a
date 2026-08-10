"""Hooks (Fase III · B4) — puntos de gancho que el núcleo dispara y los plugins escuchan."""

import logging

logger = logging.getLogger("sdk.hooks")

_HOOKS: dict = {}   # nombre → [(plugin, fn)]


def registrar_hook(nombre, fn, *, plugin=None):
    _HOOKS.setdefault(nombre, []).append((plugin, fn))
    return True


def ejecutar_hook(nombre, *args, **kwargs) -> list:
    """Dispara un hook y devuelve la lista de resultados de los handlers (bulletproof)."""
    out = []
    for plugin, fn in list(_HOOKS.get(nombre, [])):
        try:
            out.append(fn(*args, **kwargs))
        except Exception as e:
            logger.debug("hook %s (%s): %s", nombre, plugin, e)
    return out


def limpiar_plugin(plugin):
    for n in list(_HOOKS):
        _HOOKS[n] = [(p, f) for (p, f) in _HOOKS[n] if p != plugin]
