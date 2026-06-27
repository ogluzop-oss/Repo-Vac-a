"""
FASE D — KPIs financieros corporativos. Se DERIVAN de balance/PyG (contabilidad), tesoreria y
deuda viva (financiacion), sin duplicar informacion. Publica en BI. Multiempresa, auditado.
"""

import logging
from src.db.conexion import obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("finanzas.ratios")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _r(num, den):
    try:
        return round(float(num) / float(den), 4) if den else None
    except Exception:
        return None


def calcular(*, anio=None, id_empresa=None) -> dict:
    """Calcula el set completo de ratios. Reutiliza contabilidad.informes + tesoreria + deuda."""
    eid = _emp(id_empresa)
    out = {}
    pyg = balance = {}
    try:
        from src.services.contabilidad import informes
        pyg = informes.perdidas_ganancias(id_empresa=eid, anio=anio)
        balance = informes.balance_situacion(id_empresa=eid, anio=anio)
    except Exception as e:
        logger.debug("contab: %s", e)
    ingresos = float(pyg.get("ingresos", 0) or 0)
    gastos = float(pyg.get("gastos", 0) or 0)
    resultado = float(pyg.get("resultado", 0) or 0)
    activo = float(balance.get("activo", 0) or 0)
    pasivo = float(balance.get("pasivo", 0) or 0)
    patrimonio = float(balance.get("patrimonio_neto", 0) or 0)

    # Amortizaciones e intereses aproximados (cuenta 68 amortizacion / 66 gastos financieros si existen).
    amortizacion = _saldo_cuenta_prefijo("68", eid, anio)
    intereses = _saldo_cuenta_prefijo("66", eid, anio)

    # P&L derivados
    out["beneficio_neto"] = round(resultado, 2)
    out["ebit"] = round(resultado + intereses, 2)            # resultado + gastos financieros
    out["ebitda"] = round(resultado + intereses + amortizacion, 2)
    out["margen_neto"] = _pct(resultado, ingresos)
    out["margen_operativo"] = _pct(out["ebit"], ingresos)

    # Balance / estructura
    out["endeudamiento"] = _r(pasivo, activo)               # pasivo / activo
    out["solvencia"] = _r(activo, pasivo)                    # activo / pasivo
    out["roa"] = _pct(resultado, activo)                    # rentabilidad sobre activos
    out["roe"] = _pct(resultado, patrimonio)               # rentabilidad sobre fondos propios
    out["rotacion_activos"] = _r(ingresos, activo)

    # Liquidez (usa tesoreria como aproximacion del activo corriente liquido)
    disponible = pendiente_cobro = pendiente_pago = 0.0
    try:
        from src.services.tesoreria import posicion
        pos = posicion.posicion(id_empresa=eid)
        disponible = float(pos.get("disponible", 0) or 0)
        pendiente_cobro = float(pos.get("por_cobrar", 0) or 0)
        pendiente_pago = float(pos.get("comprometido", 0) or 0)
    except Exception as e:
        logger.debug("tesoreria: %s", e)
    activo_corriente = disponible + pendiente_cobro
    out["liquidez_corriente"] = _r(activo_corriente, pendiente_pago) if pendiente_pago else None
    out["prueba_acida"] = _r(disponible + pendiente_cobro, pendiente_pago) if pendiente_pago else None

    # Periodos medios + ciclo de conversion de caja
    out["periodo_medio_cobro_dias"] = _r(pendiente_cobro * 365, ingresos) if ingresos else None
    out["periodo_medio_pago_dias"] = _r(pendiente_pago * 365, gastos) if gastos else None
    pmc = out["periodo_medio_cobro_dias"] or 0
    pmp = out["periodo_medio_pago_dias"] or 0
    out["cash_conversion_cycle"] = round(pmc - pmp, 2)

    # Deuda viva (financiacion)
    try:
        from src.services.finanzas import financiacion
        out["deuda_viva"] = financiacion.deuda_viva(id_empresa=eid)["total"]
    except Exception:
        out["deuda_viva"] = 0
    return out


def _pct(num, den):
    return round(float(num) * 100 / float(den), 2) if den else None


def _saldo_cuenta_prefijo(prefijo, eid, anio):
    """Suma de saldos de apuntes de cuentas que empiezan por `prefijo` (best-effort sobre contab)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            # contab_apuntes(codigo_cuenta, debe, haber, id_empresa) + contab_asientos(fecha)
            q = ("SELECT COALESCE(SUM(ap.debe - ap.haber),0) FROM contab_apuntes ap "
                 "JOIN contab_asientos a ON a.id=ap.id_asiento WHERE ap.id_empresa=%s AND ap.codigo_cuenta LIKE %s")
            p = [eid, f"{prefijo}%"]
            if anio:
                q += " AND YEAR(a.fecha)=%s"; p.append(anio)
            cur.execute(q, p)
            r = cur.fetchone()
            return float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception:
        return 0.0


def registrar_en_bi(*, anio=None, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    k = calcular(anio=anio, id_empresa=eid)
    try:
        from src.services.bi import kpis as bi_kpis
        if hasattr(bi_kpis, "guardar_valor"):
            for nombre, valor in k.items():
                if isinstance(valor, (int, float)):
                    bi_kpis.guardar_valor(f"fin_{nombre}", valor, id_empresa=eid)
    except Exception as e:
        logger.debug("registrar_en_bi: %s", e)
    return k
