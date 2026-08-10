"""
Marketplace · Validación (Fase IV · Bloque 2). Valida un plugin ANTES de instalarlo: manifest
correcto (reutiliza `sdk.manifest`), compatibilidad de versión (min/max vs versión de la app),
integridad (checksum) y estado de firma (`firmas`). No accede a la BD.
"""

from __future__ import annotations

from src.services.marketplace import firmas
from src.platform.versioning import Version

# Versión de la plataforma/app frente a la que se comprueba compatibilidad de plugins.
APP_VERSION = "4.0.0"


def compatibilidad(manifest, *, app_version=APP_VERSION) -> tuple:
    """(ok, motivo|None) según version_minima/version_maxima del manifest vs versión de la app."""
    app = Version.parse(app_version)
    if not app.en_rango(manifest.get("version_minima"), manifest.get("version_maxima")):
        return False, (f"requiere app {manifest.get('version_minima') or '*'}.."
                       f"{manifest.get('version_maxima') or '*'} (actual {app})")
    return True, None


def validar(manifest, *, app_version=APP_VERSION, checksum_esperado=None, revocadas=()) -> dict:
    """Resultado completo de validación de un plugin."""
    from src.sdk import plugin_manifest
    ok_manifest, errores = plugin_manifest.validar(manifest)

    ok_compat, motivo = compatibilidad(manifest, app_version=app_version)
    if not ok_compat:
        errores = errores + [motivo]

    estado_firma = firmas.verificar(manifest, revocadas=revocadas)

    checksum_ok = True
    if checksum_esperado is not None:
        checksum_ok = (firmas.hash_manifest(manifest) == checksum_esperado)
        if not checksum_ok:
            errores = errores + ["checksum no coincide (contenido alterado)"]

    return {
        "ok": bool(ok_manifest) and ok_compat and checksum_ok,
        "errores": errores,
        "firma_estado": estado_firma,
        "compatible": ok_compat,
        "checksum_ok": checksum_ok,
        "hash": firmas.hash_manifest(manifest),
    }


def cumple_politica(estado_firma, politica) -> bool:
    """¿El estado de firma cumple la política de la empresa?
    politica: oficiales | firmados | internos | todos."""
    if politica == "todos":
        return True
    if politica in ("firmados", "oficiales"):
        return estado_firma == firmas.FIRMADO
    if politica == "internos":
        # Internos: se aceptan firmados o no firmados (de repos internos), pero nunca corruptos/revocados.
        return estado_firma in (firmas.FIRMADO, firmas.NO_FIRMADO)
    return estado_firma == firmas.FIRMADO


__all__ = ["APP_VERSION", "compatibilidad", "validar", "cumple_politica"]
