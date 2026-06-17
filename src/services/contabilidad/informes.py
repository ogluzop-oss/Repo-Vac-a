"""
Informes contables (E6.3) — Mayor, Balance de sumas y saldos, Balance de situación
(abreviado) y Cuenta de Pérdidas y Ganancias (abreviada).

Agregados sobre `contab_apuntes` ⨝ `contab_asientos` (estados no borrador → incluye
contabilizados, anulados y contraasientos, que netean). Multiempresa. Sin tablas.
"""

import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _filas_a_dicts, obtener_conexion)

logger = logging.getLogger("contab.informes")


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _rango(filtros, params, anio, desde, hasta):
    if anio:
        filtros.append("a.anio=%s"); params.append(int(anio))
    if desde:
        filtros.append("a.fecha>=%s"); params.append(desde)
    if hasta:
        filtros.append("a.fecha<=%s"); params.append(hasta)


def mayor(codigo_cuenta, id_empresa=None, anio=None, desde=None, hasta=None) -> dict:
    """Movimientos de una cuenta con saldo acumulado (orden cronológico)."""
    id_empresa = _empresa(id_empresa)
    filtros = ["ap.id_empresa=%s", "ap.codigo_cuenta=%s", "a.estado<>'borrador'"]
    params = [id_empresa, str(codigo_cuenta)]
    _rango(filtros, params, anio, desde, hasta)
    apuntes, sdebe, shaber, saldo = [], 0.0, 0.0, 0.0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT a.fecha, a.numero, a.concepto, ap.descripcion, ap.debe, ap.haber "
                "FROM contab_apuntes ap JOIN contab_asientos a ON a.id=ap.id_asiento "
                "WHERE " + " AND ".join(filtros) + " ORDER BY a.anio, a.numero, ap.id", tuple(params))
            for r in _filas_a_dicts(cur, cur.fetchall()):
                d = float(r["debe"] or 0); h = float(r["haber"] or 0)
                sdebe += d; shaber += h; saldo += d - h
                r["saldo"] = round(saldo, 2); apuntes.append(r)
    except Exception as e:
        logger.error("mayor(%s): %s", codigo_cuenta, e)
    return {"cuenta": str(codigo_cuenta), "apuntes": apuntes,
            "total_debe": round(sdebe, 2), "total_haber": round(shaber, 2),
            "saldo": round(saldo, 2)}


def balance_sumas_saldos(id_empresa=None, anio=None, desde=None, hasta=None) -> dict:
    """Por cuenta: Σdebe, Σhaber, saldo. Incluye totales (deben cuadrar)."""
    id_empresa = _empresa(id_empresa)
    filtros = ["ap.id_empresa=%s", "a.estado<>'borrador'"]
    params = [id_empresa]
    _rango(filtros, params, anio, desde, hasta)
    cuentas, td, th = [], 0.0, 0.0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT ap.codigo_cuenta, COALESCE(MAX(c.nombre),'') AS nombre, "
                "SUM(ap.debe) AS debe, SUM(ap.haber) AS haber "
                "FROM contab_apuntes ap JOIN contab_asientos a ON a.id=ap.id_asiento "
                "LEFT JOIN contab_cuentas c ON c.id_empresa=ap.id_empresa AND c.codigo=ap.codigo_cuenta "
                "WHERE " + " AND ".join(filtros) + " GROUP BY ap.codigo_cuenta ORDER BY ap.codigo_cuenta",
                tuple(params))
            for r in _filas_a_dicts(cur, cur.fetchall()):
                d = round(float(r["debe"] or 0), 2); h = round(float(r["haber"] or 0), 2)
                td += d; th += h
                cuentas.append({"codigo": r["codigo_cuenta"], "nombre": r["nombre"],
                                "debe": d, "haber": h, "saldo": round(d - h, 2)})
    except Exception as e:
        logger.error("balance_sumas_saldos: %s", e)
    return {"cuentas": cuentas, "total_debe": round(td, 2), "total_haber": round(th, 2),
            "cuadra": abs(round(td - th, 2)) < 0.01}


def _saldos_por_tipo(id_empresa, anio, desde, hasta) -> dict:
    """{tipo: saldo_neto(debe-haber)} agregado por `contab_cuentas.tipo`."""
    filtros = ["ap.id_empresa=%s", "a.estado<>'borrador'"]
    params = [id_empresa]
    _rango(filtros, params, anio, desde, hasta)
    out = {}
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(c.tipo,'otro') AS tipo, SUM(ap.debe-ap.haber) AS saldo "
            "FROM contab_apuntes ap JOIN contab_asientos a ON a.id=ap.id_asiento "
            "LEFT JOIN contab_cuentas c ON c.id_empresa=ap.id_empresa AND c.codigo=ap.codigo_cuenta "
            "WHERE " + " AND ".join(filtros) + " GROUP BY tipo", tuple(params))
        for r in _filas_a_dicts(cur, cur.fetchall()):
            out[r["tipo"]] = round(float(r["saldo"] or 0), 2)
    return out


def perdidas_ganancias(id_empresa=None, anio=None, desde=None, hasta=None) -> dict:
    """PyG abreviada: ingresos (grupo 7) - gastos (grupo 6) = resultado."""
    id_empresa = _empresa(id_empresa)
    try:
        t = _saldos_por_tipo(id_empresa, anio, desde, hasta)
    except Exception as e:
        logger.error("perdidas_ganancias: %s", e); t = {}
    gastos = round(t.get("gasto", 0.0), 2)            # saldo deudor (positivo)
    ingresos = round(-t.get("ingreso", 0.0), 2)       # ingresos son acreedores → -(debe-haber)
    return {"ingresos": ingresos, "gastos": gastos, "resultado": round(ingresos - gastos, 2)}


def balance_situacion(id_empresa=None, anio=None, desde=None, hasta=None) -> dict:
    """Balance de situación abreviado: Activo = Pasivo + Patrimonio neto (incl. resultado)."""
    id_empresa = _empresa(id_empresa)
    try:
        t = _saldos_por_tipo(id_empresa, anio, desde, hasta)
    except Exception as e:
        logger.error("balance_situacion: %s", e); t = {}
    activo = round(t.get("activo", 0.0), 2)            # deudor (debe-haber) positivo
    pasivo = round(-t.get("pasivo", 0.0), 2)           # acreedor → -(debe-haber)
    pn_cuentas = round(-t.get("pn", 0.0), 2)
    resultado = perdidas_ganancias(id_empresa, anio, desde, hasta)["resultado"]
    patrimonio_neto = round(pn_cuentas + resultado, 2)
    return {"activo": activo, "pasivo": pasivo, "patrimonio_neto": patrimonio_neto,
            "resultado": resultado,
            "cuadra": abs(round(activo - (pasivo + patrimonio_neto), 2)) < 0.01}
