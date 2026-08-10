"""
IOC · Impresoras — registro de identidad de impresoras (tickets, etiquetas, A4, almacén, cocina)
vinculadas a centro / terminal / empresa. Genuinamente ausente hasta ahora (existía el DRIVER de
impresión `perifericos/impresora.py`, no el registro). Multiempresa, auditado, con Event Bus.
"""

import logging
import uuid

from src.services.identidad import _base as B
from src.services.identidad.tipos import valida_tipo_impresora

logger = logging.getLogger("identidad.impresoras")


def registrar_impresora(*, codigo=None, id_centro=None, id_terminal=None, tipo="TICKETS", nombre=None,
                        backend=None, observaciones=None, id_empresa=None) -> str | None:
    id_empresa = B.emp(id_empresa)
    iid = str(uuid.uuid4())
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ioc_impresoras (id, id_empresa, id_centro, id_terminal, codigo, tipo, "
                "nombre, backend, observaciones) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (iid, id_empresa, id_centro, id_terminal, codigo, valida_tipo_impresora(tipo),
                 nombre, backend, observaciones))
            conn.commit()
        B.audit("IMPRESORA_ALTA", "ioc_impresoras", f"{iid}:{tipo}:{nombre}")
        B.evento("identidad.impresora_registrada", ref_entidad="ioc_impresoras", ref_id=iid,
                 id_empresa=id_empresa, payload={"id_centro": id_centro, "tipo": tipo})
        return iid
    except Exception as e:
        logger.error("registrar_impresora: %s", e)
        return None


def asignar(id_impresora, *, id_centro=None, id_terminal=None, id_empresa=None) -> bool:
    id_empresa = B.emp(id_empresa)
    sets, params = ["fecha_modificacion=NOW()"], []
    if id_centro is not None:
        sets.append("id_centro=%s"); params.append(id_centro)
    if id_terminal is not None:
        sets.append("id_terminal=%s"); params.append(id_terminal)
    if len(sets) == 1:
        return False
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE ioc_impresoras SET {', '.join(sets)} WHERE id=%s", (*params, id_impresora))
            conn.commit()
        B.audit("IMPRESORA_ASIGNADA", "ioc_impresoras", f"{id_impresora}")
        B.evento("identidad.impresora_asignada", ref_entidad="ioc_impresoras", ref_id=id_impresora,
                 id_empresa=id_empresa, payload={"id_centro": id_centro, "id_terminal": id_terminal})
        return True
    except Exception as e:
        logger.error("asignar: %s", e)
        return False


def listar_impresoras(*, id_empresa=None, id_centro=None, id_terminal=None, tipo=None) -> list:
    id_empresa = B.emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM ioc_impresoras WHERE id_empresa<=>%s AND archivado=0"
            p = [id_empresa]
            if id_centro is not None:
                q += " AND id_centro=%s"; p.append(id_centro)
            if id_terminal is not None:
                q += " AND id_terminal=%s"; p.append(id_terminal)
            if tipo:
                q += " AND tipo=%s"; p.append(valida_tipo_impresora(tipo))
            q += " ORDER BY fecha_alta DESC"
            cur.execute(q, p)
            return B.filas(cur)
    except Exception as e:
        logger.error("listar_impresoras: %s", e)
        return []
