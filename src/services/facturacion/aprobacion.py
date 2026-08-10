"""
FASE 4.5 — Workflow de APROBACIÓN de facturas (entornos corporativos).

Estados: borrador → pendiente_aprobacion → aprobada/rechazada → emitida → anulada.
Auditoría completa (quién/cuándo/qué). Reutiliza factura_eventos y el estado de la factura.
Compatible con el motor de Workflow/BPM existente (db.workflow) si se desea escalar por
departamento/empresa; aquí se ofrece el ciclo mínimo autónomo y auditable.
"""

import logging

logger = logging.getLogger("facturacion.aprobacion")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.facturacion.identidad_facturacion import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()


def _set(id_factura, estado, usuario=None, evento=None, detalle=None, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    from src.db import facturas_cliente as FC
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if estado == "aprobada":
                cur.execute("UPDATE facturas_cliente SET estado=%s, aprobada_por=%s, "
                            "aprobada_fecha=NOW() WHERE id_factura=%s AND id_empresa=%s",
                            (estado, usuario, id_factura, id_empresa))
            else:
                cur.execute("UPDATE facturas_cliente SET estado=%s WHERE id_factura=%s "
                            "AND id_empresa=%s", (estado, id_factura, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
        if ok:
            FC.registrar_evento(id_factura, evento or estado, detalle=detalle, usuario=usuario,
                                id_empresa=id_empresa)
        return ok
    except Exception as e:
        logger.error("aprobacion._set(%s,%s): %s", id_factura, estado, e); return False


def enviar_a_aprobacion(id_factura, usuario=None, id_empresa=None) -> bool:
    return _set(id_factura, "pendiente_aprobacion", usuario, "enviada_aprobacion", id_empresa=id_empresa)


def aprobar(id_factura, usuario=None, id_empresa=None) -> bool:
    return _set(id_factura, "aprobada", usuario, "aprobada", id_empresa=id_empresa)


def rechazar(id_factura, usuario=None, motivo=None, id_empresa=None) -> bool:
    return _set(id_factura, "rechazada", usuario, "rechazada", detalle=motivo, id_empresa=id_empresa)


def pendientes(id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    from src.db.conexion import _filas_a_dicts, obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_factura, numero, total, id_cliente FROM facturas_cliente "
                        "WHERE id_empresa=%s AND estado='pendiente_aprobacion' ORDER BY id_factura DESC",
                        (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("aprobacion.pendientes: %s", e); return []
