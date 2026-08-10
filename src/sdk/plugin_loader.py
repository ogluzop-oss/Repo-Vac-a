"""
Plugin Loader (Fase III · B4) — carga dinámica de plugins.

Lee el manifest, importa el módulo del plugin y llama a su punto de entrada `register(sdk)` para que
registre sus hooks/extensiones. Carga segura (best-effort sandbox: solo se invoca `register`; los
errores no rompen el host). Compatibilidad por versión declarada en el manifest.
"""

import importlib
import importlib.util
import logging
import os

from src.sdk import plugin_manifest as _man
from src.sdk import plugin_registry as _reg

logger = logging.getLogger("sdk.loader")

VERSION_HOST = "3.0"


def _sdk_api():
    """Objeto `sdk` que se pasa al plugin (superficie controlada de extensión)."""
    from src.sdk import extension_points, hooks
    from types import SimpleNamespace
    return SimpleNamespace(registrar_extension=extension_points.registrar_extension,
                           registrar_hook=hooks.registrar_hook,
                           version_host=VERSION_HOST)


def cargar_plugin(ruta_dir, *, id_empresa=None) -> dict:
    """Carga un plugin desde su carpeta (con manifest.json + __init__.py). Devuelve {ok, clave, error}."""
    manifest = _man.cargar(ruta_dir)
    ok, errores = _man.validar(manifest or {})
    if not ok:
        return {"ok": False, "error": f"manifest inválido: {errores}"}
    clave = manifest["clave"]
    # Compatibilidad por versión (host >= min_host declarado).
    min_host = str(manifest.get("min_host", "0"))
    if min_host > VERSION_HOST:
        return {"ok": False, "clave": clave, "error": f"requiere host >= {min_host}"}
    try:
        init = os.path.join(ruta_dir, "__init__.py")
        spec = importlib.util.spec_from_file_location(f"plugin_{clave}", init)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "register"):
            mod.register(_sdk_api())   # el plugin registra sus contribuciones
    except Exception as e:
        logger.error("cargar_plugin(%s): %s", clave, e)
        return {"ok": False, "clave": clave, "error": str(e)}
    _reg.instalar(clave, manifest, ruta=ruta_dir, id_empresa=id_empresa)
    return {"ok": True, "clave": clave}


def cargar_todos(directorio="plugins", *, id_empresa=None) -> list:
    """Carga todos los plugins de un directorio (cada subcarpeta con manifest.json)."""
    resultados = []
    base = directorio if os.path.isabs(directorio) else os.path.join(os.getcwd(), directorio)
    if not os.path.isdir(base):
        return resultados
    for nombre in sorted(os.listdir(base)):
        sub = os.path.join(base, nombre)
        if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "manifest.json")):
            resultados.append(cargar_plugin(sub, id_empresa=id_empresa))
    return resultados
