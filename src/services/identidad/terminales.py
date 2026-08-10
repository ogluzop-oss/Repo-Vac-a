"""
IOC · Terminales — identidad propia de cada TPV/PDA/dispositivo (UUID interno permanente + atributos:
código, tipo, nombre, estado, última conexión, versión sw, sync, IP, MAC, SO, nº serie). Genuinamente
ausente hasta ahora. Multiempresa, auditado, con Event Bus. No sustituye al driver de cobro
(`tpv/card_terminal_service`), que es otra cosa.
"""

import logging
import uuid

from src.services.identidad import _base as B
from src.services.identidad.tipos import valida_tipo_dispositivo

logger = logging.getLogger("identidad.terminales")


def registrar_terminal(*, codigo_terminal=None, id_centro=None, tipo_dispositivo="TPV", nombre=None,
                       numero_serie=None, mac=None, ip=None, sistema_operativo=None, version_sw=None,
                       observaciones=None, id_empresa=None) -> str | None:
    id_empresa = B.emp(id_empresa)
    tid = str(uuid.uuid4())
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ioc_terminales (id, id_empresa, id_centro, codigo_terminal, tipo_dispositivo, "
                "nombre, numero_serie, mac, ip, sistema_operativo, version_sw, observaciones) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (tid, id_empresa, id_centro, codigo_terminal, valida_tipo_dispositivo(tipo_dispositivo),
                 nombre, numero_serie, mac, ip, sistema_operativo, version_sw, observaciones))
            conn.commit()
        B.audit("TERMINAL_ALTA", "ioc_terminales", f"{tid}:{tipo_dispositivo}:{nombre}")
        B.evento("identidad.terminal_registrado", ref_entidad="ioc_terminales", ref_id=tid,
                 id_empresa=id_empresa, payload={"id_centro": id_centro, "tipo": tipo_dispositivo})
        return tid
    except Exception as e:
        logger.error("registrar_terminal: %s", e)
        return None


def asignar_centro(id_terminal, id_centro, *, id_empresa=None) -> bool:
    id_empresa = B.emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE ioc_terminales SET id_centro=%s, fecha_modificacion=NOW() WHERE id=%s",
                        (id_centro, id_terminal))
            conn.commit()
        B.audit("TERMINAL_ASIGNADO", "ioc_terminales", f"{id_terminal}->{id_centro}")
        B.evento("identidad.terminal_asignado", ref_entidad="ioc_terminales", ref_id=id_terminal,
                 id_empresa=id_empresa, payload={"id_centro": id_centro})
        return True
    except Exception as e:
        logger.error("asignar_centro: %s", e)
        return False


def heartbeat(id_terminal, *, version_sw=None, ip=None, sincronizado=False) -> bool:
    """Marca la última conexión (y opcionalmente versión/IP/última sync) de un terminal vivo."""
    sets = ["ultima_conexion=NOW()"]
    params = []
    if version_sw is not None:
        sets.append("version_sw=%s"); params.append(version_sw)
    if ip is not None:
        sets.append("ip=%s"); params.append(ip)
    if sincronizado:
        sets.append("ultima_sync=NOW()")
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE ioc_terminales SET {', '.join(sets)} WHERE id=%s", (*params, id_terminal))
            conn.commit()
        return True
    except Exception as e:
        logger.error("heartbeat: %s", e)
        return False


def cambiar_estado(id_terminal, estado, *, id_empresa=None) -> bool:
    id_empresa = B.emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE ioc_terminales SET estado=%s, fecha_modificacion=NOW() WHERE id=%s",
                        (estado, id_terminal))
            conn.commit()
        B.audit("TERMINAL_ESTADO", "ioc_terminales", f"{id_terminal}:{estado}")
        return True
    except Exception as e:
        logger.error("cambiar_estado: %s", e)
        return False


def obtener_terminal(id_terminal):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ioc_terminales WHERE id=%s", (id_terminal,))
            return B.fila(cur)
    except Exception as e:
        logger.error("obtener_terminal: %s", e)
        return None


def listar_terminales(*, id_empresa=None, id_centro=None, estado=None, incluir_archivados=False) -> list:
    id_empresa = B.emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM ioc_terminales WHERE id_empresa<=>%s"
            p = [id_empresa]
            if id_centro is not None:
                q += " AND id_centro=%s"; p.append(id_centro)
            if estado:
                q += " AND estado=%s"; p.append(estado)
            if not incluir_archivados:
                q += " AND archivado=0"
            q += " ORDER BY fecha_alta DESC"
            cur.execute(q, p)
            return B.filas(cur)
    except Exception as e:
        logger.error("listar_terminales: %s", e)
        return []
