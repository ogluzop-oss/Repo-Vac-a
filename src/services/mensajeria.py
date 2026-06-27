"""
Mensajería interna (FASE COM-6).

Conversaciones con participantes y mensajes. Alcance: usuario / departamento / tienda / empresa.
Multiempresa y auditado. Sin dependencias de tiempo real (polling desde la GUI).
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("mensajeria")
ALCANCES = ("usuario", "departamento", "tienda", "empresa")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_conversacion(asunto, participantes, *, alcance="usuario", ambito_id=None,
                       creado_por=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    _gate("comunicaciones", id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO conversaciones (id_empresa, asunto, alcance, ambito_id, creado_por) "
                        "VALUES (%s,%s,%s,%s,%s)", (id_empresa, asunto, alcance, ambito_id, creado_por))
            cid = cur.lastrowid
            for u in set(list(participantes or []) + ([creado_por] if creado_por else [])):
                cur.execute("INSERT IGNORE INTO conversaciones_participantes (id_empresa, id_conversacion, "
                            "usuario) VALUES (%s,%s,%s)", (id_empresa, cid, u))
            conn.commit()
        _audit("MENSAJE_ENVIADO", f"conversacion={cid} creada")
        return cid
    except Exception as e:
        logger.error("crear_conversacion: %s", e)
        return None


def enviar_mensaje(id_conversacion, emisor, cuerpo, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO mensajes (id_empresa, id_conversacion, emisor, cuerpo) "
                        "VALUES (%s,%s,%s,%s)", (id_empresa, id_conversacion, emisor, cuerpo))
            mid = cur.lastrowid
            conn.commit()
        _audit("MENSAJE_ENVIADO", f"conversacion={id_conversacion} msg={mid}")
        return mid
    except Exception as e:
        logger.error("enviar_mensaje: %s", e)
        return None


def leer(id_conversacion, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM mensajes WHERE id_conversacion=%s AND id_empresa=%s ORDER BY fecha",
                        (id_conversacion, id_empresa))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("leer: %s", e)
        return []


def conversaciones_de(usuario, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT c.* FROM conversaciones c JOIN conversaciones_participantes p "
                        "ON p.id_conversacion=c.id WHERE c.id_empresa=%s AND p.usuario=%s "
                        "AND c.estado='activa' ORDER BY c.id DESC", (id_empresa, usuario))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("conversaciones_de: %s", e)
        return []


def archivar(id_conversacion, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE conversaciones SET estado='archivada' WHERE id=%s AND id_empresa=%s",
                        (id_conversacion, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("archivar: %s", e)
        return False


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("sistema", accion, "mensajes", detalle)
    except Exception:
        pass

def _gate(modulo, id_empresa):
    """Enforcement SaaS (legacy-safe): bloquea si el plan no incluye el módulo."""
    try:
        from src.services.saas import enforcement as _enf
        _enf.exigir_modulo(modulo, id_empresa)
    except ImportError:
        pass
