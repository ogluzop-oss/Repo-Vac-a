"""
Cash flow (rama Tesorería, FASE 6).

Construye el flujo de caja agrupado por periodo (diario / semanal / mensual / anual) en dos
escenarios:
  • real     → movimientos de tesorería ya registrados (importe con signo).
  • previsto → vencimientos pendientes (COBRO = entrada, PAGO = salida) por fecha de vencimiento.
Cada periodo lleva entradas, salidas, neto y acumulado. Solo lectura.
"""

import datetime as _dt

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

GRANULARIDADES = ("diario", "semanal", "mensual", "anual")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _a_fecha(f):
    if isinstance(f, (_dt.date, _dt.datetime)):
        return f if isinstance(f, _dt.date) and not isinstance(f, _dt.datetime) else f.date()
    return _dt.datetime.strptime(str(f)[:10], "%Y-%m-%d").date()


def _clave(fecha, gran):
    d = _a_fecha(fecha)
    if gran == "diario":
        return d.strftime("%Y-%m-%d")
    if gran == "semanal":
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if gran == "anual":
        return d.strftime("%Y")
    return d.strftime("%Y-%m")        # mensual (defecto)


def _acumular(buckets: dict) -> list:
    """Ordena los periodos y añade el acumulado corrido."""
    out = []
    acum = 0.0
    for k in sorted(buckets):
        b = buckets[k]
        neto = round(b["entradas"] - b["salidas"], 2)
        acum = round(acum + neto, 2)
        out.append({"periodo": k, "entradas": round(b["entradas"], 2),
                    "salidas": round(b["salidas"], 2), "neto": neto, "acumulado": acum})
    return out


def flujo_real(id_empresa=None, desde=None, hasta=None, granularidad="mensual") -> list:
    """Flujo de caja realizado a partir de movimientos_tesoreria."""
    id_empresa = _emp(id_empresa)
    gran = granularidad if granularidad in GRANULARIDADES else "mensual"
    q = "SELECT fecha, importe FROM movimientos_tesoreria WHERE id_empresa=%s"
    p = [id_empresa]
    if desde:
        q += " AND fecha>=%s"; p.append(desde)
    if hasta:
        q += " AND fecha<=%s"; p.append(hasta)
    buckets = {}
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(q, p)
        for r in cur.fetchall():
            d = r if isinstance(r, dict) else dict(zip([c[0] for c in cur.description], r))
            k = _clave(d["fecha"], gran)
            imp = float(d["importe"] or 0)
            b = buckets.setdefault(k, {"entradas": 0.0, "salidas": 0.0})
            if imp >= 0:
                b["entradas"] += imp
            else:
                b["salidas"] += -imp
    return _acumular(buckets)


def flujo_previsto(id_empresa=None, desde=None, hasta=None, granularidad="mensual") -> list:
    """Flujo de caja previsto a partir de vencimientos pendientes (por fecha de vencimiento)."""
    id_empresa = _emp(id_empresa)
    gran = granularidad if granularidad in GRANULARIDADES else "mensual"
    q = ("SELECT fecha_vencimiento AS fecha, tipo, pendiente FROM vencimientos WHERE id_empresa=%s "
         "AND estado IN ('PENDIENTE','PARCIAL','VENCIDO')")
    p = [id_empresa]
    if desde:
        q += " AND fecha_vencimiento>=%s"; p.append(desde)
    if hasta:
        q += " AND fecha_vencimiento<=%s"; p.append(hasta)
    buckets = {}
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(q, p)
        for r in cur.fetchall():
            d = r if isinstance(r, dict) else dict(zip([c[0] for c in cur.description], r))
            k = _clave(d["fecha"], gran)
            pend = float(d["pendiente"] or 0)
            b = buckets.setdefault(k, {"entradas": 0.0, "salidas": 0.0})
            if d["tipo"] == "COBRO":
                b["entradas"] += pend
            else:
                b["salidas"] += pend
    return _acumular(buckets)


def flujo(id_empresa=None, desde=None, hasta=None, granularidad="mensual", escenario="real") -> list:
    """Punto de entrada único: escenario 'real' o 'previsto'."""
    if escenario == "previsto":
        return flujo_previsto(id_empresa, desde, hasta, granularidad)
    return flujo_real(id_empresa, desde, hasta, granularidad)
