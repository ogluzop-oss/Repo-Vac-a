"""
Incident Response (OBS-6): registro y ciclo de vida de incidentes de seguridad.
Estados abierto/investigando/mitigado/cerrado. Eventos auditados. Multiempresa.
"""

import logging
from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("seguridad.incidentes")
TIPOS = ("acceso_sospechoso", "fuerza_bruta", "token_comprometido", "uso_anomalo", "posible_fuga", "otro")
ESTADOS = ("abierto", "investigando", "mitigado", "cerrado")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def abrir(tipo, *, severidad="media", id_usuario=None, ip_origen=None, detalle=None, id_empresa=None) -> int | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO incidentes_seguridad (id_empresa, tipo, severidad, id_usuario, "
                        "ip_origen, detalle) VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_empresa, tipo, severidad, id_usuario, ip_origen, detalle))
            iid = cur.lastrowid
            cur.execute("INSERT INTO eventos_incidentes (id_incidente, accion, detalle) VALUES (%s,'ABIERTO',%s)",
                        (iid, detalle))
            conn.commit()
        _audit("INCIDENTE_ABIERTO", f"id={iid} {tipo} sev={severidad}")
        # Notifica a administradores (best-effort).
        try:
            from src.services import notificaciones
            notificaciones.emitir("seguridad", f"Incidente: {tipo}", detalle or "", modulo="seguridad",
                                  prioridad="critica", roles=["ADMINISTRADOR"], id_empresa=id_empresa)
        except Exception:
            pass
        return iid
    except Exception as e:
        logger.error("abrir: %s", e)
        return None


def cambiar_estado(id_incidente, estado, *, usuario=None, detalle=None) -> bool:
    if estado not in ESTADOS:
        raise ValueError(f"estado inválido: {estado}")
    cierre = ", cerrado_en=NOW()" if estado == "cerrado" else ""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE incidentes_seguridad SET estado=%s{cierre} WHERE id=%s", (estado, id_incidente))
            cur.execute("INSERT INTO eventos_incidentes (id_incidente, accion, usuario, detalle) "
                        "VALUES (%s,%s,%s,%s)", (id_incidente, estado.upper(), usuario, detalle))
            conn.commit()
        _audit(f"INCIDENTE_{estado.upper()}", f"id={id_incidente}")
        return True
    except ValueError:
        raise
    except Exception as e:
        logger.error("cambiar_estado: %s", e)
        return False


def listar(*, estado=None, id_empresa=None) -> list:
    q = "SELECT * FROM incidentes_seguridad WHERE 1=1"
    p = []
    if id_empresa is not None:
        q += " AND id_empresa=%s"; p.append(id_empresa)
    if estado:
        q += " AND estado=%s"; p.append(estado)
    q += " ORDER BY creado_en DESC LIMIT 500"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar: %s", e)
        return []


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("seguridad", accion, "incidentes_seguridad", detalle)
    except Exception:
        pass
