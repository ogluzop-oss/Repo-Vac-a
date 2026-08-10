"""
Plugin SDK (Fase III · B4) — fachada pública.

Permite ampliar Smart Manager AI sin modificar el núcleo: manifest.json + puntos de extensión + hooks +
carga dinámica + registro persistente. API-First (sin PyQt).

    from src import sdk
    sdk.cargar_plugin("plugins/ejemplo")
    sdk.extensiones("menus")
"""

from src.sdk.plugin_loader import cargar_plugin, cargar_todos  # noqa: F401
from src.sdk.plugin_registry import instalar, desinstalar, listar_instalados  # noqa: F401
from src.sdk.extension_points import registrar_extension, extensiones  # noqa: F401
from src.sdk.hooks import registrar_hook, ejecutar_hook  # noqa: F401
from src.sdk import plugin_manifest as manifest  # noqa: F401

__all__ = ["cargar_plugin", "cargar_todos", "instalar", "desinstalar", "listar_instalados",
           "registrar_extension", "extensiones", "registrar_hook", "ejecutar_hook", "manifest"]
