"""
Marketplace · Actualización (Fase IV · Bloque 2). Detecta y aplica actualizaciones comparando la
versión instalada (Plugin SDK) con la disponible en el catálogo (SemVer). Registra la acción en el
historial (reutiliza `instalacion`). Multiempresa.
"""

from __future__ import annotations

import json

from src.platform.versioning import Version
from src.services.marketplace import catalogo, instalacion


def _instalados(id_empresa) -> dict:
    try:
        from src import sdk
        return {p.get("clave"): p for p in sdk.listar_instalados(id_empresa)}
    except Exception:
        return {}


def hay_actualizacion(clave, id_empresa=None) -> dict:
    inst = _instalados(id_empresa).get(clave)
    disp = catalogo.catalogo_manifests(id_empresa).get(clave)
    if not inst or not disp:
        return {"clave": clave, "actualizable": False}
    v_inst = Version.parse(inst.get("version"))
    v_disp = Version.parse(disp.get("version"))
    return {"clave": clave, "actualizable": v_disp > v_inst,
            "instalada": str(v_inst), "disponible": str(v_disp)}


def actualizaciones_disponibles(id_empresa=None) -> list:
    salida = []
    disp = catalogo.catalogo_manifests(id_empresa)
    for clave, inst in _instalados(id_empresa).items():
        if clave in disp:
            info = hay_actualizacion(clave, id_empresa)
            if info["actualizable"]:
                salida.append(info)
    return salida


def actualizar(clave, *, id_empresa=None, usuario=None, **kw) -> dict:
    """Aplica la actualización si la hay (instala la versión del catálogo y lo marca en el historial)."""
    info = hay_actualizacion(clave, id_empresa)
    if not info.get("actualizable"):
        return {"ok": False, "clave": clave, "errores": ["no hay actualización disponible"], **info}
    res = instalacion.instalar(clave, id_empresa=id_empresa, usuario=usuario, **kw)
    if res.get("ok"):
        # Marca la acción como 'actualizar' en el historial (el instalar ya registró 'instalar').
        m = catalogo.catalogo_manifests(id_empresa).get(clave) or {}
        instalacion._hist(clave, "actualizar", id_empresa=id_empresa, manifest=m, usuario=usuario)
    return {**res, "desde": info.get("instalada"), "hasta": info.get("disponible")}


__all__ = ["hay_actualizacion", "actualizaciones_disponibles", "actualizar"]
