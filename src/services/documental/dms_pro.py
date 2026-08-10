"""
DMS PRO (Módulo 19, enriquecimiento de Documentación). Añade SOLO lo ausente sobre el centro
documental existente (`documentos_registro`): VERSIONADO de documentos, RETENCIÓN/caducidad (con
archivado/purga por Scheduler) y ETIQUETAS/clasificación. Referencia `documentos_registro` por
`id_documento`; no lo reescribe. Multiempresa, auditado. No duplica.
"""

import datetime as _dt
import logging

logger = logging.getLogger("documental.pro")

_POLITICAS = {"fiscal": 365 * 6, "laboral": 365 * 4, "mercantil": 365 * 6, "general": 365 * 3,
              "temporal": 365}


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.documental.identidad_documental import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("documental", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Versionado ───────────────────────────────────────────────────────────────
def nueva_version(id_documento, *, ruta=None, hash_documental=None, nota=None, usuario=None,
                  id_empresa=None) -> dict:
    """Registra una nueva versión del documento (autoincrementa el nº de versión)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(version),0) FROM documento_versiones WHERE id_documento=%s",
                        (id_documento,))
            r = cur.fetchone()
            ver = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) + 1
            cur.execute("INSERT INTO documento_versiones (id_empresa, id_documento, version, ruta, "
                        "hash_documental, nota, usuario) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_documento, ver, ruta, hash_documental, nota, usuario))
            c.commit()
        _audit("VERSION_NUEVA", f"doc{id_documento} v{ver}", "documento_versiones")
        return {"ok": True, "version": ver}
    except Exception as e:
        logger.error("nueva_version: %s", e)
        return {"ok": False, "motivo": str(e)}


def versiones(id_documento, *, id_empresa=None) -> list:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM documento_versiones WHERE id_documento=%s ORDER BY version DESC",
                        (id_documento,))
            return _filas(cur)
    except Exception as e:
        logger.error("versiones: %s", e)
        return []


# ── Retención / caducidad ────────────────────────────────────────────────────
def fijar_retencion(id_documento, *, politica="general", fecha_caducidad=None, fecha_base=None,
                    id_empresa=None) -> dict:
    """Fija la política de retención. Si no se da `fecha_caducidad`, se calcula desde `fecha_base`
    (o hoy) + los días de la política."""
    emp = _emp(id_empresa)
    if not fecha_caducidad:
        base = fecha_base or _dt.date.today().isoformat()
        try:
            fecha_caducidad = (_dt.date.fromisoformat(str(base)[:10]) +
                               _dt.timedelta(days=_POLITICAS.get(politica, 365 * 3))).isoformat()
        except Exception:
            fecha_caducidad = None
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO documento_retencion (id_empresa, id_documento, politica, "
                        "fecha_caducidad) VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                        "politica=VALUES(politica), fecha_caducidad=VALUES(fecha_caducidad)",
                        (emp, id_documento, politica, fecha_caducidad))
            c.commit()
        _audit("RETENCION", f"doc{id_documento} {politica}->{fecha_caducidad}", "documento_retencion")
        return {"ok": True, "fecha_caducidad": fecha_caducidad}
    except Exception as e:
        logger.error("fijar_retencion: %s", e)
        return {"ok": False, "motivo": str(e)}


def documentos_caducados(id_empresa=None, *, a_fecha=None) -> list:
    emp = _emp(id_empresa)
    a_fecha = a_fecha or _dt.date.today().isoformat()
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM documento_retencion WHERE id_empresa<=>%s AND archivado=0 "
                        "AND fecha_caducidad IS NOT NULL AND fecha_caducidad<=%s", (emp, a_fecha))
            return _filas(cur)
    except Exception as e:
        logger.error("documentos_caducados: %s", e)
        return []


def _job_retencion_documental(id_empresa=None) -> dict:
    """Job de scheduler: archiva los documentos cuya retención ha caducado (no borra el fichero: los
    marca archivados y avisa). La purga física queda a decisión explícita."""
    emp = _emp(id_empresa)
    caducados = documentos_caducados(emp)
    if not caducados:
        return {"archivados": 0}
    try:
        from src.db.conexion import obtener_conexion
        ids = [d["id_documento"] for d in caducados]
        with obtener_conexion() as c, c.cursor() as cur:
            cur.executemany("UPDATE documento_retencion SET archivado=1 WHERE id_documento=%s",
                            [(i,) for i in ids])
            c.commit()
        _audit("RETENCION_ARCHIVADO", f"{len(ids)} docs", "documento_retencion")
    except Exception as e:
        logger.debug("_job_retencion_documental: %s", e)
    return {"archivados": len(caducados)}


def registrar_jobs_documental(id_empresa=None):
    try:
        from src.services import scheduler
        scheduler.registrar("documental_retencion", _job_retencion_documental)
        scheduler.registrar_job("documental_retencion", intervalo_horas=168,
                                descripcion="Archivado de documentos con retención caducada")
    except Exception as e:
        logger.debug("registrar_jobs_documental: %s", e)


# ── Etiquetas / clasificación ────────────────────────────────────────────────
def etiquetar(id_documento, etiquetas, *, id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    if isinstance(etiquetas, str):
        etiquetas = [etiquetas]
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            for et in etiquetas:
                cur.execute("INSERT IGNORE INTO documento_etiquetas (id_empresa, id_documento, etiqueta) "
                            "VALUES (%s,%s,%s)", (emp, id_documento, str(et)[:60].strip().lower()))
            c.commit()
        _audit("ETIQUETADO", f"doc{id_documento}:{','.join(map(str, etiquetas))}", "documento_etiquetas")
        return {"ok": True}
    except Exception as e:
        logger.error("etiquetar: %s", e)
        return {"ok": False, "motivo": str(e)}


def buscar_por_etiqueta(etiqueta, *, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id_documento FROM documento_etiquetas WHERE id_empresa<=>%s "
                        "AND etiqueta=%s", (emp, str(etiqueta).strip().lower()))
            return [r["id_documento"] for r in _filas(cur)]
    except Exception as e:
        logger.error("buscar_por_etiqueta: %s", e)
        return []


def etiquetas_de(id_documento) -> list:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT etiqueta FROM documento_etiquetas WHERE id_documento=%s ORDER BY etiqueta",
                        (id_documento,))
            return [r["etiqueta"] for r in _filas(cur)]
    except Exception as e:
        logger.error("etiquetas_de: %s", e)
        return []
