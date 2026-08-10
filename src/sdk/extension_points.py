"""
Extension Points (Fase III · B4) — puntos de extensión donde los plugins registran contribuciones.

Un plugin registra menús/pantallas/acciones/permisos/eventos/workflows/comunicaciones/API/widgets/
informes SIN tocar el núcleo. El host consulta `extensiones(punto)` para descubrirlas.
"""

PUNTOS = ("menus", "pantallas", "acciones", "permisos", "eventos", "workflows", "comunicaciones",
          "api", "widgets", "informes")

_EXT: dict = {p: [] for p in PUNTOS}


def registrar_extension(punto, contribucion, *, plugin=None):
    """Registra una contribución en un punto de extensión. `contribucion` es libre (dict/callable)."""
    if punto not in _EXT:
        _EXT[punto] = []
    _EXT[punto].append({"plugin": plugin, "valor": contribucion})
    return True


def extensiones(punto=None):
    if punto:
        return list(_EXT.get(punto, []))
    return {p: list(v) for p, v in _EXT.items()}


def limpiar_plugin(plugin):
    """Elimina todas las contribuciones de un plugin (desinstalación segura)."""
    for p in list(_EXT):
        _EXT[p] = [e for e in _EXT[p] if e.get("plugin") != plugin]
