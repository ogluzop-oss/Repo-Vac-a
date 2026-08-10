"""
Delegacion temporal de responsabilidades (Paquete Enterprise 7, SUBFASE 7.4). Un responsable
ausente (vacaciones/baja/permiso) delega TEMPORALMENTE en otro usuario, que asume aprobaciones,
notificaciones, workflow, copiloto y agentes — SIN cambiar el responsable real.
"""

import logging

from src.services.gobierno import organigrama as _O

logger = logging.getLogger("gobierno.delegacion")


def _emp(id_empresa=None):
    return _O._emp(id_empresa)


def delegar(usuario_origen, usuario_delegado, *, motivo=None, desde=None, hasta=None,
            id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO org_delegaciones (id_empresa, usuario_origen, usuario_delegado, "
                        "motivo, desde, hasta, activa) VALUES (%s,%s,%s,%s,%s,%s,1)",
                        (emp, str(usuario_origen)[:80], str(usuario_delegado)[:80],
                         (motivo or "")[:120], desde, hasta))
            did = cur.lastrowid
            c.commit()
        # Auditoria corporativa (SUBFASE 7.11).
        try:
            from src.db.conexion import log_auditoria
            log_auditoria("gobierno", "DELEGACION_CREADA", "org_delegaciones",
                          f"{usuario_origen}->{usuario_delegado} ({motivo})")
        except Exception:
            pass
        return did
    except Exception as e:
        logger.error("delegar: %s", e)
        return None


def revocar(id_delegacion, id_empresa=None) -> bool:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE org_delegaciones SET activa=0 WHERE id=%s AND id_empresa=%s",
                        (id_delegacion, emp))
            c.commit()
        return True
    except Exception:
        return False


def _vigentes(emp, campo, usuario):
    from src.db.conexion import _filas_a_dicts, obtener_conexion
    with obtener_conexion() as c, c.cursor() as cur:
        cur.execute(f"SELECT * FROM org_delegaciones WHERE id_empresa=%s AND {campo}=%s AND activa=1 "
                    "AND (desde IS NULL OR desde<=NOW()) AND (hasta IS NULL OR hasta>=NOW())",
                    (emp, str(usuario)))
        return _filas_a_dicts(cur, cur.fetchall())


def delega_a(usuario_origen, id_empresa=None) -> str | None:
    """Delegado vigente de un responsable ausente (o None)."""
    try:
        v = _vigentes(_emp(id_empresa), "usuario_origen", usuario_origen)
        return v[0]["usuario_delegado"] if v else None
    except Exception:
        return None


def sustituye_a(usuario_delegado, id_empresa=None) -> list:
    """Responsables a los que este usuario sustituye actualmente (asume su autoridad)."""
    try:
        return [d["usuario_origen"] for d in _vigentes(_emp(id_empresa), "usuario_delegado", usuario_delegado)]
    except Exception:
        return []


def activas(id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM org_delegaciones WHERE id_empresa=%s AND activa=1 "
                        "AND (hasta IS NULL OR hasta>=NOW())", (emp,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception:
        return []
