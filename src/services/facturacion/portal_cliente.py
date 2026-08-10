"""
FASE 4.4 — Portal del CLIENTE (consulta y descarga de documentación).

Expone, para un cliente, sus documentos (facturas/abonos/rectificativas/vencimientos/cobros) y
permite descargarlos (PDF/Facturae) reutilizando el servicio de distribución. Registra la
trazabilidad: PORTAL_LOGIN / PORTAL_VISUALIZACION / PORTAL_DESCARGA (portal_cliente_log).
"""

import logging

logger = logging.getLogger("facturacion.portal_cliente")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.facturacion.identidad_facturacion import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()


def registrar_acceso(id_cliente, evento, id_factura=None, detalle=None, ip=None, id_empresa=None) -> bool:
    """Traza del portal: PORTAL_LOGIN | PORTAL_VISUALIZACION | PORTAL_DESCARGA."""
    id_empresa = _emp(id_empresa)
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO portal_cliente_log (id_empresa, id_cliente, evento, id_factura, "
                        "detalle, ip) VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_cliente, str(evento)[:30], id_factura, detalle, ip))
            conn.commit()
        return True
    except Exception as e:
        logger.error("portal.registrar_acceso: %s", e); return False


def documentos_cliente(id_cliente, id_empresa=None) -> dict:
    """Documentación del cliente para el portal: facturas + vencimientos. Registra VISUALIZACION."""
    id_empresa = _emp(id_empresa)
    from src.db import facturas_cliente as FC
    out = {"facturas": [], "vencimientos": []}
    try:
        out["facturas"] = FC.listar_facturas(id_empresa=id_empresa, id_cliente=id_cliente)
    except Exception:
        pass
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, importe, pendiente, estado, fecha_vencimiento, concepto "
                        "FROM vencimientos WHERE id_empresa=%s AND tipo='COBRO' "
                        "AND id_documento IN (SELECT id_factura FROM facturas_cliente "
                        "WHERE id_cliente=%s AND id_empresa=%s) ORDER BY fecha_vencimiento",
                        (id_empresa, id_cliente, id_empresa))
            out["vencimientos"] = _filas_a_dicts(cur, cur.fetchall())
    except Exception:
        pass
    registrar_acceso(id_cliente, "PORTAL_VISUALIZACION", id_empresa=id_empresa)
    return out


def descargar(id_cliente, id_factura, formato="pdf", id_empresa=None) -> str | None:
    """Descarga (PDF/Facturae) de una factura del cliente. Registra PORTAL_DESCARGA."""
    id_empresa = _emp(id_empresa)
    from src.services.facturacion import distribucion as D
    ruta = D.exportar_factura(id_factura, formato, id_empresa)
    registrar_acceso(id_cliente, "PORTAL_DESCARGA", id_factura=id_factura, detalle=formato,
                     id_empresa=id_empresa)
    return ruta
