"""
Marketplace · Instalación (Fase IV · Bloque 2). Instalar / actualizar / desinstalar / reinstalar /
rollback / verificar integridad. REUTILIZA el Plugin SDK (`sdk.registry`) para el estado instalado y
registra cada acción en `plugins_historial` (para rollback). Valida política + firma + dependencias +
licencia antes de instalar. Multiempresa. Publica eventos por el Corporate Event Bus (vía el SDK).
"""

from __future__ import annotations

import json
import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion
from src.services.marketplace import catalogo, dependencias, licencias, validacion

logger = logging.getLogger("marketplace.instalacion")


def _hist(clave, accion, *, id_empresa=None, manifest=None, usuario=None):
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO plugins_historial (id_empresa, clave, version, accion, manifest, ruta, "
                "usuario) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, clave, (manifest or {}).get("version"), accion,
                 json.dumps(manifest) if manifest else None, (manifest or {}).get("_ruta"), usuario))
            conn.commit()
    except Exception as e:
        logger.debug("_hist(%s,%s): %s", clave, accion, e)


def historial(clave, id_empresa=None) -> list:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM plugins_historial WHERE clave=%s AND (id_empresa=%s OR "
                        "(%s IS NULL AND id_empresa IS NULL)) ORDER BY id DESC",
                        (clave, id_empresa, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("historial(%s): %s", clave, e)
        return []


def instalar(clave, *, id_empresa=None, usuario=None, politica="firmados", revocadas=(),
             requerir_licencia=False, _cat=None) -> dict:
    """Instala un plugin (y sus dependencias) validando política/firma/compatibilidad/licencia."""
    cat = _cat if _cat is not None else catalogo.catalogo_manifests(id_empresa)
    manifest = cat.get(clave)
    if not manifest:
        return {"ok": False, "clave": clave, "errores": ["plugin no encontrado en el catálogo"]}

    # 1) Validación (manifest + compatibilidad + firma + checksum).
    val = validacion.validar(manifest, revocadas=revocadas)
    if not val["ok"]:
        return {"ok": False, "clave": clave, "errores": val["errores"], "firma": val["firma_estado"]}
    if not validacion.cumple_politica(val["firma_estado"], politica):
        return {"ok": False, "clave": clave, "firma": val["firma_estado"],
                "errores": [f"la política '{politica}' no admite firma '{val['firma_estado']}'"]}

    # 2) Licencia (gate opcional; abierto por defecto sin cobro).
    if not licencias.tiene_licencia(clave, id_empresa=id_empresa, requerir=requerir_licencia):
        return {"ok": False, "clave": clave, "errores": ["sin licencia válida"]}

    # 3) Dependencias: orden topológico (dependencias primero).
    orden, problemas = dependencias.orden_instalacion(clave, cat)
    if not orden:
        return {"ok": False, "clave": clave, "errores": ["dependencias no resolubles"],
                "problemas": problemas}

    # 4) Instalar en orden (reutiliza el SDK; publica eventos).
    from src import sdk
    instalados = []
    for k in orden:
        m = cat.get(k)
        if sdk.instalar(k, m, ruta=m.get("_ruta"), id_empresa=id_empresa, usuario=usuario):
            _hist(k, "instalar", id_empresa=id_empresa, manifest=m, usuario=usuario)
            instalados.append(k)
    return {"ok": clave in instalados, "clave": clave, "instalados": instalados,
            "firma": val["firma_estado"], "problemas": problemas}


def desinstalar(clave, *, id_empresa=None, usuario=None) -> dict:
    from src import sdk
    ok = sdk.desinstalar(clave, id_empresa=id_empresa)
    if ok:
        _hist(clave, "desinstalar", id_empresa=id_empresa, usuario=usuario)
    return {"ok": ok, "clave": clave}


def reinstalar(clave, *, id_empresa=None, usuario=None, **kw) -> dict:
    desinstalar(clave, id_empresa=id_empresa, usuario=usuario)
    return instalar(clave, id_empresa=id_empresa, usuario=usuario, **kw)


def rollback(clave, *, id_empresa=None, usuario=None) -> dict:
    """Vuelve a la versión ANTERIOR instalada (según el historial). Reutiliza el SDK."""
    hist = [h for h in historial(clave, id_empresa) if h.get("accion") in ("instalar", "actualizar")]
    if len(hist) < 2:
        return {"ok": False, "clave": clave, "errores": ["no hay versión anterior a la que volver"]}
    anterior = hist[1]     # hist[0] = versión actual; hist[1] = anterior
    try:
        manifest = json.loads(anterior.get("manifest") or "{}")
    except Exception:
        manifest = {}
    if not manifest.get("clave"):
        return {"ok": False, "clave": clave, "errores": ["manifest anterior no disponible"]}
    from src import sdk
    ok = sdk.instalar(clave, manifest, ruta=manifest.get("_ruta"), id_empresa=id_empresa,
                      usuario=usuario)
    if ok:
        _hist(clave, "rollback", id_empresa=id_empresa, manifest=manifest, usuario=usuario)
    return {"ok": ok, "clave": clave, "version": manifest.get("version")}


def verificar_integridad(clave, *, id_empresa=None) -> dict:
    """Compara el manifest instalado con el disponible en el catálogo (hash)."""
    from src import sdk
    from src.services.marketplace import firmas
    instalado = next((p for p in sdk.listar_instalados(id_empresa) if p.get("clave") == clave), None)
    if not instalado:
        return {"ok": False, "clave": clave, "errores": ["no instalado"]}
    try:
        m_inst = json.loads(instalado.get("manifest") or "{}")
    except Exception:
        m_inst = {}
    disponible = catalogo.catalogo_manifests(id_empresa).get(clave)
    h_inst = firmas.hash_manifest(m_inst)
    h_disp = firmas.hash_manifest(disponible) if disponible else None
    return {"ok": (h_disp is None or h_inst == h_disp), "clave": clave,
            "hash_instalado": h_inst, "hash_catalogo": h_disp,
            "firma": firmas.verificar(m_inst)}


__all__ = ["historial", "instalar", "desinstalar", "reinstalar", "rollback", "verificar_integridad"]
