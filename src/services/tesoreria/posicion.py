"""
Posición de tesorería en tiempo real (rama Tesorería, FASE 5).

Calcula, a partir de los saldos reales de las cuentas (FASE 1-2) y de los vencimientos
pendientes (FASE 3):
  • disponible   = Σ saldo real de las cuentas activas
  • comprometido = Σ pendiente de vencimientos PAGO (lo que se debe)
  • por_cobrar   = Σ pendiente de vencimientos COBRO (lo que nos deben)
  • previsto     = disponible + por_cobrar − comprometido
  • futuro       = previsto considerando solo vencimientos hasta `horizonte_dias`
Agrupaciones: empresa, tienda y cuenta. Solo lectura; no escribe nada.
"""

import datetime as _dt

from src.db import tesoreria as _T
from src.db import vencimientos as _V
from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _pendiente(id_empresa, tipo, hasta=None) -> float:
    q = ("SELECT COALESCE(SUM(pendiente),0) FROM vencimientos WHERE id_empresa=%s AND tipo=%s "
         "AND estado IN ('PENDIENTE','PARCIAL','VENCIDO')")
    p = [id_empresa, tipo]
    if hasta:
        q += " AND fecha_vencimiento<=%s"; p.append(hasta)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(q, p)
        r = cur.fetchone()
        return round(float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0), 2)


def disponible_por_cuenta(id_empresa=None, id_tienda=None) -> list:
    """Saldo real de cada cuenta activa (opcionalmente filtrado por tienda)."""
    id_empresa = _emp(id_empresa)
    out = []
    for c in _T.listar_cuentas(id_tienda=id_tienda, id_empresa=id_empresa):
        out.append({"id_cuenta": c["id"], "nombre_cuenta": c["nombre_cuenta"],
                    "id_tienda": c.get("id_tienda"), "moneda": c.get("moneda", "EUR"),
                    "saldo": _T.saldo_cuenta(c["id"], id_empresa)})
    return out


def posicion(id_empresa=None, id_tienda=None, horizonte_dias=None) -> dict:
    """Posición de tesorería consolidada. Si `horizonte_dias`, calcula también el saldo
    futuro considerando los vencimientos hasta esa fecha."""
    id_empresa = _emp(id_empresa)
    cuentas = disponible_por_cuenta(id_empresa, id_tienda)
    disponible = round(sum(c["saldo"] for c in cuentas), 2)
    comprometido = _pendiente(id_empresa, "PAGO")
    por_cobrar = _pendiente(id_empresa, "COBRO")
    previsto = round(disponible + por_cobrar - comprometido, 2)
    res = {
        "id_empresa": id_empresa,
        "id_tienda": id_tienda,
        "disponible": disponible,
        "comprometido": comprometido,
        "por_cobrar": por_cobrar,
        "previsto": previsto,
        "por_cuenta": cuentas,
    }
    if horizonte_dias:
        hasta = (_dt.date.today() + _dt.timedelta(days=int(horizonte_dias))).strftime("%Y-%m-%d")
        cobrar_h = _pendiente(id_empresa, "COBRO", hasta)
        pagar_h = _pendiente(id_empresa, "PAGO", hasta)
        res["horizonte_dias"] = int(horizonte_dias)
        res["por_cobrar_horizonte"] = cobrar_h
        res["comprometido_horizonte"] = pagar_h
        res["futuro"] = round(disponible + cobrar_h - pagar_h, 2)
    return res
