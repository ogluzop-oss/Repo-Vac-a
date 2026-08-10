"""Helpers compartidos por los servicios IOC: contexto de empresa, auditoría, event bus y cursores."""

import logging

logger = logging.getLogger("identidad")


def emp(id_empresa=None):
    """Resuelve la empresa activa (multiempresa). Reutiliza el contexto existente."""
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return id_empresa


def usuario_actual():
    try:
        from src.db.usuario import sesion_global
        return sesion_global.obtener_nombre()
    except Exception:
        return None


def audit(accion, tabla, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("identidad", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def evento(tipo, *, ref_entidad=None, ref_id=None, id_empresa=None, payload=None):
    """Publica en el Event Bus existente (nunca crea un bus paralelo). Best-effort."""
    try:
        from src.services import eventos
        eventos.publicar(tipo, ref_entidad=ref_entidad, ref_id=ref_id, id_empresa=id_empresa,
                         payload=payload or {})
    except Exception as e:
        logger.debug("evento(%s): %s", tipo, e)


def filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def fila(cur):
    from src.db.conexion import _fila_a_dict
    return _fila_a_dict(cur, cur.fetchone())
