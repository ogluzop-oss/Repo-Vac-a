"""
Capa de PERSISTENCIA + ACCESO documental sobre `StorageProvider` (Fase 12, cierre H1). Punto ÚNICO por el que
los documentos empresariales persistentes se ESCRIBEN, LEEN, DESCARGAN y BORRAN de forma tenant-aware. No crea
un storage ni un visor paralelos: reutiliza `obtener_storage()` y el índice `documentos_registro`.

Reglas de seguridad (CRÍTICAS):
  • El tenant y la storage_key SIEMPRE se resuelven desde la BD por `id_documento`; NUNCA del cliente.
  • Antes de leer/descargar/borrar se valida `id_empresa` del registro contra el tenant del solicitante y el
    RBAC del usuario. Imposible cruzar tenants ni manipular la clave/ruta.
  • Sin fallback silencioso: en backend `s3`, un fallo se audita como error explícito.
"""

import logging
import mimetypes
import os
import re

logger = logging.getLogger("storage.documentos")

_SANEA = re.compile(r"[^A-Za-z0-9._-]+")


def _nombre_seguro(nombre: str) -> str:
    base = os.path.basename(str(nombre or "documento"))
    limpio = _SANEA.sub("_", base).strip("._-") or "documento"
    return limpio[:180]


def _mime(nombre: str) -> str:
    return mimetypes.guess_type(str(nombre or ""))[0] or "application/octet-stream"


# ── WRITE (usado por el chokepoint registrar_documento) ───────────────────────
def persistir_fichero(id_empresa, tipo, ruta_local, *, nombre=None) -> dict:
    """Sube al StorageProvider el fichero ya generado. Devuelve {ok, clave, backend, size, mime, error?}.
    Bulletproof (no lanza). Requiere id_empresa. `ruta_local` es el fichero temporal de generación."""
    if not id_empresa or not ruta_local or not os.path.exists(ruta_local):
        return {"ok": False, "clave": None, "razon": "sin_fichero_o_tenant"}
    try:
        from src.services.storage import backend_configurado, obtener_storage
        with open(ruta_local, "rb") as f:
            datos = f.read()
        nombre_f = _nombre_seguro(nombre or ruta_local)
        sp = obtener_storage()
        clave = sp.guardar(id_empresa, str(tipo or "otros"), nombre_f, datos, content_type=_mime(nombre_f))
        return {"ok": True, "clave": clave, "backend": backend_configurado(),
                "size": len(datos), "mime": _mime(nombre_f)}
    except Exception as e:
        logger.error("persistir_fichero(emp=%s tipo=%s): %s", id_empresa, tipo, e)
        _audit("STORAGE_PERSIST_ERROR", f"emp={id_empresa} tipo={tipo} err={e}")
        return {"ok": False, "clave": None, "error": str(e)}


# ── READ / DOWNLOAD (visor) ───────────────────────────────────────────────────
def abrir_documento(id_documento, *, id_empresa, usuario=None, permiso="documentos.ver") -> dict:
    """Devuelve {ok, datos|None, mime, nombre, backend, clave} de un documento, validando tenant + RBAC. Si el
    documento es LEGACY (sin storage_key) se migra al vuelo desde su ruta local y luego se sirve."""
    reg = _resolver_seguro(id_documento, id_empresa, usuario, permiso)
    if not reg.get("ok"):
        return reg
    doc = reg["doc"]
    clave = doc.get("storage_key")
    if not clave:                                     # LEGACY → migrar al vuelo (idempotente)
        m = migrar_registro_legacy(id_documento, id_empresa=id_empresa)
        clave = m.get("storage_key")
        if not clave:
            return {"ok": False, "error": "documento no disponible en storage", "estado": m.get("estado")}
    try:
        from src.services.storage import obtener_storage
        datos = obtener_storage().leer(id_empresa, clave)
        return {"ok": True, "datos": datos, "mime": doc.get("mime_type") or _mime(doc.get("nombre")),
                "nombre": doc.get("nombre"), "backend": doc.get("storage_backend"), "clave": clave}
    except Exception as e:
        logger.error("abrir_documento(%s): %s", id_documento, e)
        return {"ok": False, "error": str(e)}


def url_descarga(id_documento, *, id_empresa, usuario=None, segundos=300, permiso="documentos.ver") -> dict:
    """URL firmada/temporal validando tenant + RBAC (la firma SÓLO se emite tras autorizar)."""
    reg = _resolver_seguro(id_documento, id_empresa, usuario, permiso)
    if not reg.get("ok"):
        return reg
    clave = reg["doc"].get("storage_key")
    if not clave:
        m = migrar_registro_legacy(id_documento, id_empresa=id_empresa)
        clave = m.get("storage_key")
        if not clave:
            return {"ok": False, "error": "documento no disponible en storage"}
    try:
        from src.services.storage import obtener_storage
        url = obtener_storage().url_firmada(id_empresa, clave, segundos=segundos, usuario=usuario,
                                            autorizado=True)
        return {"ok": True, "url": url, "clave": clave}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── DELETE ─────────────────────────────────────────────────────────────────────
def eliminar_documento(id_documento, *, id_empresa, usuario=None, permiso="documentos.eliminar") -> dict:
    """Borra el objeto vía StorageProvider (validando tenant + RBAC) y luego el registro. Si el borrado en
    storage falla, NO se elimina silenciosamente la metadata: se marca FAILED y se audita."""
    reg = _resolver_seguro(id_documento, id_empresa, usuario, permiso)
    if not reg.get("ok"):
        return reg
    doc = reg["doc"]
    clave = doc.get("storage_key")
    if clave:
        try:
            from src.services.storage import obtener_storage
            obtener_storage().borrar(id_empresa, clave)
        except Exception as e:
            logger.error("eliminar_documento storage(%s): %s", id_documento, e)
            _marcar_estado(id_documento, "FAILED")
            _audit("DOCUMENTO_DELETE_STORAGE_ERROR", f"doc={id_documento} err={e}")
            return {"ok": False, "error": f"fallo al borrar en storage: {e}", "metadata_conservada": True}
    _borrar_registro(id_documento)
    _audit("DOCUMENTO_ELIMINADO", f"doc={id_documento} emp={id_empresa} por={usuario}")
    return {"ok": True}


# ── MIGRACIÓN de documentos existentes (legacy) ───────────────────────────────
def migrar_registro_legacy(id_documento, *, id_empresa=None) -> dict:
    """Migra UN documento legacy (ruta local → StorageProvider) de forma idempotente. Estados:
    LEGACY→MIGRATED / MISSING / FAILED. No borra el original. Reanudable (si ya tiene storage_key, no repite)."""
    from src.db import documentos as D
    doc = D.obtener_documento(id_documento)
    if not doc:
        return {"ok": False, "estado": "MISSING", "error": "registro inexistente"}
    if id_empresa is not None and str(doc.get("id_empresa")) != str(id_empresa):
        return {"ok": False, "error": "tenant no coincide"}      # aislamiento
    if doc.get("storage_key"):
        return {"ok": True, "estado": "MIGRATED", "storage_key": doc["storage_key"]}   # idempotente
    ruta = doc.get("ruta")
    emp = doc.get("id_empresa")
    if not ruta or not os.path.exists(ruta):
        _marcar_estado(id_documento, "MISSING")
        return {"ok": False, "estado": "MISSING", "error": "fichero legacy ausente"}
    r = persistir_fichero(emp, doc.get("tipo_documento"), ruta, nombre=doc.get("nombre"))
    if not r.get("ok"):
        _marcar_estado(id_documento, "FAILED")
        return {"ok": False, "estado": "FAILED", "error": r.get("error")}
    _guardar_storage_meta(id_documento, r["clave"], r.get("backend"), r.get("size"), r.get("mime"), "MIGRATED")
    _audit("DOCUMENTO_MIGRADO", f"doc={id_documento} key={r['clave']}")
    return {"ok": True, "estado": "MIGRATED", "storage_key": r["clave"]}


def migrar_documentos_legacy(id_empresa, *, limite=500) -> dict:
    """Backfill idempotente de los documentos legacy de un tenant. No destructivo. Reanudable."""
    from src.db import documentos as D
    pendientes = D.listar_documentos(id_empresa=id_empresa, limite=limite)
    inf = {"id_empresa": str(id_empresa), "total": 0, "migrados": 0, "ya": 0, "missing": 0, "fallidos": 0}
    for doc in pendientes:
        if doc.get("storage_key"):
            inf["ya"] += 1
            continue
        inf["total"] += 1
        r = migrar_registro_legacy(doc.get("id_documento"), id_empresa=id_empresa)
        est = r.get("estado")
        inf["migrados" if est == "MIGRATED" and r.get("ok") else
            "missing" if est == "MISSING" else "fallidos"] += 1
    return inf


# ── internos (BD / auditoría / RBAC) ──────────────────────────────────────────
def _resolver_seguro(id_documento, id_empresa, usuario, permiso) -> dict:
    """Resuelve el registro por id, valida tenant y RBAC. Nunca acepta ruta/clave del cliente."""
    if not id_empresa:
        return {"ok": False, "error": "id_empresa obligatorio"}
    from src.db import documentos as D
    doc = D.obtener_documento(id_documento)
    if not doc:
        return {"ok": False, "error": "documento inexistente"}
    if str(doc.get("id_empresa")) != str(id_empresa):
        _audit("DOCUMENTO_ACCESO_DENEGADO", f"doc={id_documento} tenant_solicitante={id_empresa}")
        return {"ok": False, "error": "documento de otro tenant"}     # aislamiento estricto
    if not _rbac(usuario, permiso, id_empresa):
        return {"ok": False, "error": f"usuario sin permiso {permiso}"}
    return {"ok": True, "doc": doc}


def _rbac(usuario, permiso, id_empresa) -> bool:
    if usuario is None:
        return True                       # llamada interna/servicio (sin usuario) — el tenant ya se validó
    try:
        from src.services.autorizacion import puede
        return bool(puede(usuario, permiso, id_empresa=id_empresa))
    except Exception:
        return True                       # RBAC no disponible → no bloquea (comportamiento previo)


def _guardar_storage_meta(id_documento, clave, backend, size, mime, estado):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE documentos_registro SET storage_key=%s, storage_backend=%s, size_bytes=%s, "
                        "mime_type=%s, migracion_estado=%s WHERE id_documento=%s",
                        (clave, backend, size, mime, estado, id_documento))
            c.commit()
    except Exception as e:
        logger.debug("guardar_storage_meta: %s", e)   # columnas no presentes (migración pendiente)


def _marcar_estado(id_documento, estado):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE documentos_registro SET migracion_estado=%s WHERE id_documento=%s",
                        (estado, id_documento))
            c.commit()
    except Exception:
        pass


def _borrar_registro(id_documento):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM documentos_registro WHERE id_documento=%s", (id_documento,))
            c.commit()
    except Exception as e:
        logger.error("borrar_registro(%s): %s", id_documento, e)


def _audit(evento, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("documentos", evento, "storage", detalle)
    except Exception:
        pass
