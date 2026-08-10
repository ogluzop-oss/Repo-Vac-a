"""
Cola de distribucion + confirmaciones (Fase 2, SUBFASE 2.4/2.5/2.6).

`distribucion_pendiente` guarda una fila por (evento x destino). El envio marca ENVIADO y
crea un ACK PENDIENTE por terminal; la terminal confirma (recibido/aplicado/rechazado). Ante
error, se reprograma el proximo intento segun la politica de reintentos. Nada se pierde:
un evento para una terminal offline permanece en la cola hasta que se confirme.
"""

import json
import logging
import uuid as _uuid
from datetime import datetime

from src.services.distribucion import reintentos as _R

logger = logging.getLogger("distribucion.cola")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def _dicts(cur, rows):
    try:
        from src.db.conexion import _filas_a_dicts
        return _filas_a_dicts(cur, rows)
    except Exception:
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in rows]


def encolar(evento: dict, destino: dict, *, sincronizacion="PROGRAMADA", prioridad="MEDIA",
            fecha_programada=None, id_empresa=None) -> int | None:
    """Encola un evento para un destino. Devuelve el id de distribucion o None."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        payload = evento.get("payload")
        pj = json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else None
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO distribucion_pendiente (uuid, id_evento, uuid_evento, tipo_evento, "
                "id_empresa, id_tienda, destino, tipo_destino, destino_tienda, prioridad, "
                "sincronizacion, estado, fecha_programada, payload, hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDIENTE',%s,%s,%s)",
                (str(_uuid.uuid4()), evento.get("id"), evento.get("uuid"), evento.get("tipo"),
                 emp, int(evento.get("id_tienda") or 0), destino["destino"],
                 destino.get("tipo_destino", "terminal"), destino.get("id_tienda"),
                 prioridad, sincronizacion, fecha_programada, pj, evento.get("hash")))
            did = cur.lastrowid
            c.commit()
            return did
    except Exception as e:
        logger.error("encolar: %s", e)
        return None


def pendientes(*, sincronizacion=None, estado="PENDIENTE", destino=None, hasta=None,
               id_empresa=None, limite=1000) -> list:
    emp = _emp(id_empresa)
    try:
        q = "SELECT * FROM distribucion_pendiente WHERE id_empresa=%s AND estado=%s"
        p = [emp, estado]
        if sincronizacion:
            q += " AND sincronizacion=%s"; p.append(sincronizacion)
        if destino:
            q += " AND destino=%s"; p.append(destino)
        if hasta:
            q += " AND (fecha_programada IS NULL OR fecha_programada<=%s)"; p.append(hasta)
        q += " ORDER BY FIELD(prioridad,'CRITICA','ALTA','MEDIA','BAJA','INFORMATIVA'), id LIMIT %s"
        p.append(int(limite))
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(q, p)
            return _dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("pendientes: %s", e)
        return []


def marcar_enviado(id_distribucion, *, terminal=None, id_empresa=None) -> bool:
    """Marca ENVIADO y crea el ACK PENDIENTE para la terminal destino."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT destino, id_evento, destino_tienda FROM distribucion_pendiente "
                        "WHERE id=%s AND id_empresa=%s", (id_distribucion, emp))
            r = cur.fetchone()
            if not r:
                return False
            dest = (r[0] if not isinstance(r, dict) else r["destino"])
            id_evt = (r[1] if not isinstance(r, dict) else r["id_evento"])
            dt = (r[2] if not isinstance(r, dict) else r["destino_tienda"]) or 0
            term = terminal or dest
            cur.execute("UPDATE distribucion_pendiente SET estado='ENVIADO', fecha_envio=NOW() "
                        "WHERE id=%s AND id_empresa=%s", (id_distribucion, emp))
            cur.execute("INSERT INTO distribucion_confirmaciones (id_empresa, id_distribucion, "
                        "id_evento, terminal, id_tienda, estado) VALUES (%s,%s,%s,%s,%s,'PENDIENTE') "
                        "ON DUPLICATE KEY UPDATE estado='PENDIENTE', fecha=NOW()",
                        (emp, id_distribucion, id_evt, str(term)[:80], int(dt)))
            c.commit()
            return True
    except Exception as e:
        logger.error("marcar_enviado(%s): %s", id_distribucion, e)
        return False


def confirmar(id_distribucion, *, terminal, estado="APLICADO", detalle=None, id_empresa=None) -> bool:
    """ACK de una terminal: recibido/aplicado/rechazado. Actualiza la fila de distribucion."""
    emp = _emp(id_empresa)
    estado = str(estado or "APLICADO").upper()
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO distribucion_confirmaciones (id_empresa, id_distribucion, "
                        "terminal, estado, detalle) VALUES (%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE estado=VALUES(estado), detalle=VALUES(detalle), fecha=NOW()",
                        (emp, id_distribucion, str(terminal)[:80], estado, (detalle or "")[:255]))
            if estado in ("APLICADO", "RECIBIDO"):
                cur.execute("UPDATE distribucion_pendiente SET estado='CONFIRMADO', "
                            "fecha_confirmacion=NOW() WHERE id=%s AND id_empresa=%s",
                            (id_distribucion, emp))
            elif estado == "RECHAZADO":
                cur.execute("UPDATE distribucion_pendiente SET estado='RECHAZADO' "
                            "WHERE id=%s AND id_empresa=%s", (id_distribucion, emp))
            c.commit()
            return True
    except Exception as e:
        logger.error("confirmar(%s): %s", id_distribucion, e)
        return False


def marcar_error(id_distribucion, error, *, id_empresa=None) -> bool:
    """Registra un error y reprograma el proximo intento (o marca ERROR si se agota)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT reintentos FROM distribucion_pendiente WHERE id=%s AND id_empresa=%s",
                        (id_distribucion, emp))
            r = cur.fetchone()
            if not r:
                return False
            n = int((r[0] if not isinstance(r, dict) else r["reintentos"]) or 0)
            if _R.agotado(n, emp):
                cur.execute("UPDATE distribucion_pendiente SET estado='ERROR', reintentos=%s, "
                            "error=%s WHERE id=%s AND id_empresa=%s",
                            (n + 1, str(error)[:255], id_distribucion, emp))
            else:
                prox = _R.siguiente(n, emp)
                cur.execute("UPDATE distribucion_pendiente SET estado='PENDIENTE', reintentos=%s, "
                            "proximo_intento=%s, error=%s WHERE id=%s AND id_empresa=%s",
                            (n + 1, prox, str(error)[:255], id_distribucion, emp))
            c.commit()
            return True
    except Exception as e:
        logger.error("marcar_error(%s): %s", id_distribucion, e)
        return False


def confirmaciones(id_distribucion, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM distribucion_confirmaciones WHERE id_empresa=%s AND "
                        "id_distribucion=%s ORDER BY id", (emp, id_distribucion))
            return _dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("confirmaciones: %s", e)
        return []
