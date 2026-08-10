"""Plugin Manifest (Fase III · B4) — lectura/validación del manifest.json de un plugin."""

import json
import logging
import os

logger = logging.getLogger("sdk.manifest")

REQUERIDOS = ("clave", "nombre", "version")


def cargar(ruta) -> dict | None:
    """Carga un manifest.json (ruta a fichero o a carpeta que lo contenga)."""
    if os.path.isdir(ruta):
        ruta = os.path.join(ruta, "manifest.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.debug("cargar manifest %s: %s", ruta, e)
        return None


def validar(manifest) -> tuple:
    """(ok, errores[]). Comprueba campos requeridos y tipos básicos."""
    errores = []
    if not isinstance(manifest, dict):
        return False, ["manifest no es un objeto"]
    for c in REQUERIDOS:
        if not manifest.get(c):
            errores.append(f"falta '{c}'")
    for lista in ("dependencias", "permisos", "eventos", "menus"):
        if lista in manifest and not isinstance(manifest[lista], list):
            errores.append(f"'{lista}' debe ser lista")
    return (not errores), errores
