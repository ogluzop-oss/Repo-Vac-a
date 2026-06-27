"""
Calculadores de KPIs por dominio (FASE BI-3..BI-9).

Cada función devuelve {codigo_kpi: valor} para una empresa y rango. REUTILIZA los servicios
analíticos existentes (tesorería, contabilidad, IVA/AEAT, facturas) y consulta agregada de las
tablas operativas — NUNCA duplica lógica de negocio. Todo best-effort: un fallo de origen
devuelve el KPI a 0 sin romper el snapshot.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("bi.calculadores")


def _num(cur):
    r = cur.fetchone()
    if not r:
        return 0.0
    v = r[0] if not isinstance(r, dict) else list(r.values())[0]
    return float(v or 0)


def _scalar(sql, params):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return _num(cur)
    except Exception as e:
        logger.debug("scalar: %s", e)
        return 0.0


def ventas(id_empresa, desde, hasta) -> dict:
    out = {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), COALESCE(SUM(total),0) FROM ventas WHERE id_empresa=%s "
                        "AND fecha BETWEEN %s AND %s", (id_empresa, f"{desde} 00:00:00", f"{hasta} 23:59:59"))
            r = cur.fetchone()
            v = list(r.values()) if isinstance(r, dict) else r
            n, fac = int(v[0] or 0), float(v[1] or 0)
        out["ventas.facturacion"] = round(fac, 2)
        out["ventas.num_tickets"] = n
        out["ventas.ticket_medio"] = round(fac / n, 2) if n else 0.0
    except Exception as e:
        logger.debug("ventas: %s", e)
    try:
        from src.db import facturas_cliente as FC
        m = FC.informe_margenes(desde=desde, hasta=hasta, id_empresa=id_empresa) or {}
        out["ventas.margen_bruto"] = round(float(m.get("margen") or m.get("margen_total") or 0), 2)
    except Exception:
        pass
    return out


def compras(id_empresa, desde, hasta) -> dict:
    out = {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(base+iva),0), COUNT(DISTINCT id_proveedor) FROM compras_facturas "
                        "WHERE id_empresa=%s AND fecha_factura BETWEEN %s AND %s", (id_empresa, desde, hasta))
            r = cur.fetchone()
            v = list(r.values()) if isinstance(r, dict) else r
            out["compras.gasto_total"] = round(float(v[0] or 0), 2)
            out["compras.proveedores_activos"] = int(v[1] or 0)
    except Exception as e:
        logger.debug("compras: %s", e)
    return out


def inventario(id_empresa, desde, hasta) -> dict:
    out = {}
    # Valor del inventario (Stock_total * precio) — aproximación desde articulos.
    out["inventario.valor"] = round(_scalar(
        "SELECT COALESCE(SUM(Stock_total*COALESCE(precio,0)),0) FROM articulos", ()), 2)
    # Salidas por venta del periodo (rotación base) desde el kárdex.
    out["inventario.salidas"] = round(_scalar(
        "SELECT COALESCE(SUM(cantidad),0) FROM movimientos_stock WHERE id_empresa=%s "
        "AND tipo_movimiento='SALIDA_VENTA' AND DATE(fecha_movimiento) BETWEEN %s AND %s",
        (id_empresa, desde, hasta)), 2)
    # Roturas/sobreventa registradas (ventas_errores).
    out["inventario.roturas"] = round(_scalar(
        "SELECT COUNT(*) FROM ventas_errores WHERE id_empresa=%s", (id_empresa,)), 0) \
        if _tabla_existe("ventas_errores") else 0.0
    return out


def rrhh(id_empresa, desde, hasta) -> dict:
    out = {}
    anio = int(str(desde)[:4])
    out["rrhh.coste_laboral"] = round(_scalar(
        "SELECT COALESCE(SUM(bruto),0) FROM rrhh_nominas WHERE id_empresa=%s AND anio=%s",
        (id_empresa, anio)), 2)
    out["rrhh.plantilla_activa"] = round(_scalar(
        "SELECT COUNT(*) FROM rrhh_empleados WHERE id_empresa=%s AND estado='activo'", (id_empresa,)), 0)
    out["rrhh.vacaciones_pendientes"] = round(_scalar(
        "SELECT COUNT(*) FROM rrhh_vacaciones WHERE id_empresa=%s AND estado='pendiente'", (id_empresa,)), 0)
    return out


def tesoreria(id_empresa, desde, hasta) -> dict:
    out = {}
    try:
        from src.services.tesoreria import posicion as P
        pos = P.posicion(id_empresa)
        out["tesoreria.disponible"] = round(float(pos.get("disponible") or 0), 2)
        out["tesoreria.comprometido"] = round(float(pos.get("comprometido") or 0), 2)
        out["tesoreria.previsto"] = round(float(pos.get("previsto") or 0), 2)
        out["tesoreria.por_cobrar"] = round(float(pos.get("por_cobrar") or 0), 2)
    except Exception as e:
        logger.debug("tesoreria: %s", e)
    return out


def contabilidad(id_empresa, desde, hasta) -> dict:
    out = {}
    anio = int(str(desde)[:4])
    try:
        from src.services.contabilidad import informes as INF
        pyg = INF.perdidas_ganancias(id_empresa=id_empresa, anio=anio) or {}
        out["contabilidad.resultado"] = round(float(pyg.get("resultado") or pyg.get("beneficio") or 0), 2)
    except Exception as e:
        logger.debug("contabilidad: %s", e)
    return out


def aeat(id_empresa, desde, hasta) -> dict:
    out = {}
    anio = int(str(desde)[:4])
    try:
        from src.services.contabilidad import iva as IVA
        r = IVA.resumen_303(id_empresa=id_empresa, anio=anio) or {}
        out["aeat.iva_repercutido"] = round(float(r.get("iva_devengado_cuota") or 0), 2)
        out["aeat.iva_soportado"] = round(float(r.get("iva_deducible_cuota") or 0), 2)
        out["aeat.iva_neto"] = round(float(r.get("resultado") or 0), 2)
    except Exception as e:
        logger.debug("aeat: %s", e)
    return out


def _tabla_existe(nombre):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE %s", (nombre,))
            return cur.fetchone() is not None
    except Exception:
        return False


# Dominio → (función, definiciones KPI [(codigo, nombre, unidad, sentido)])
DOMINIOS = {
    "ventas": (ventas, [
        ("ventas.facturacion", "Facturación", "€", "mayor"),
        ("ventas.num_tickets", "Nº de tickets", "ud", "mayor"),
        ("ventas.ticket_medio", "Ticket medio", "€", "mayor"),
        ("ventas.margen_bruto", "Margen bruto", "€", "mayor")]),
    "compras": (compras, [
        ("compras.gasto_total", "Gasto en compras", "€", "menor"),
        ("compras.proveedores_activos", "Proveedores activos", "ud", "mayor")]),
    "inventario": (inventario, [
        ("inventario.valor", "Valor de inventario", "€", "mayor"),
        ("inventario.salidas", "Salidas por venta", "ud", "mayor"),
        ("inventario.roturas", "Roturas de stock", "ud", "menor")]),
    "rrhh": (rrhh, [
        ("rrhh.coste_laboral", "Coste laboral", "€", "menor"),
        ("rrhh.plantilla_activa", "Plantilla activa", "ud", "mayor"),
        ("rrhh.vacaciones_pendientes", "Vacaciones pendientes", "ud", "menor")]),
    "tesoreria": (tesoreria, [
        ("tesoreria.disponible", "Tesorería disponible", "€", "mayor"),
        ("tesoreria.comprometido", "Tesorería comprometida", "€", "menor"),
        ("tesoreria.previsto", "Tesorería prevista", "€", "mayor"),
        ("tesoreria.por_cobrar", "Pendiente de cobro", "€", "mayor")]),
    "contabilidad": (contabilidad, [
        ("contabilidad.resultado", "Resultado del ejercicio", "€", "mayor")]),
    "aeat": (aeat, [
        ("aeat.iva_repercutido", "IVA repercutido", "€", "mayor"),
        ("aeat.iva_soportado", "IVA soportado", "€", "mayor"),
        ("aeat.iva_neto", "IVA neto (303)", "€", "menor")]),
}
