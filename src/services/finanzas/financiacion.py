"""
FASE B — Deuda y financiacion (prestamo/leasing/renting/poliza). Cuadro de amortizacion frances
(cuota constante) con desglose interes/principal/saldo vivo. Genera vencimientos en TESORERIA
(no duplica): cada cuota -> crear_vencimiento PAGO. Auditado, multiempresa.
"""

import datetime as _dt
import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("finanzas.financiacion")
TIPOS = ("prestamo", "leasing", "renting", "poliza")
_MESES = {"mensual": 1, "trimestral": 3, "semestral": 6, "anual": 12}


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _cuota_francesa(capital, i_periodo, n):
    """Cuota constante (sistema frances). i_periodo = interes por periodo (decimal)."""
    if n <= 0:
        return 0.0
    if i_periodo == 0:
        return round(capital / n, 2)
    return round(capital * i_periodo / (1 - (1 + i_periodo) ** (-n)), 2)


def cuadro_amortizacion(capital, tipo_interes_anual, num_cuotas, *, periodicidad="mensual",
                        fecha_inicio=None, valor_residual=0) -> list:
    """Devuelve el cuadro [{numero,fecha,cuota,interes,principal,saldo_vivo}] sin persistir."""
    meses = _MESES.get(periodicidad, 1)
    i = float(tipo_interes_anual) / 100 * meses / 12
    amortizable = float(capital) - float(valor_residual)
    cuota = _cuota_francesa(amortizable, i, num_cuotas)
    fecha = fecha_inicio or _dt.date.today()
    if isinstance(fecha, str):
        fecha = _dt.datetime.strptime(fecha[:10], "%Y-%m-%d").date()
    saldo = float(capital)
    cuadro = []
    for k in range(1, num_cuotas + 1):
        interes = round((saldo - valor_residual) * i, 2) if i else 0.0
        principal = round(cuota - interes, 2)
        if k == num_cuotas:                       # ultima cuota ajusta el residual
            principal = round(saldo - valor_residual, 2)
            cuota_k = round(principal + interes, 2)
        else:
            cuota_k = cuota
        saldo = round(saldo - principal, 2)
        cuadro.append({"numero": k, "fecha": _suma_meses(fecha, meses * k), "cuota": cuota_k,
                       "interes": interes, "principal": principal, "saldo_vivo": max(saldo, 0.0)})
    return cuadro


def _suma_meses(fecha, meses):
    m = fecha.month - 1 + meses
    y = fecha.year + m // 12
    m = m % 12 + 1
    import calendar
    d = min(fecha.day, calendar.monthrange(y, m)[1])
    return _dt.date(y, m, d)


def crear_financiacion(tipo, capital, tipo_interes_anual, num_cuotas, *, periodicidad="mensual",
                       entidad=None, codigo=None, fecha_inicio=None, valor_residual=0, id_cuenta=None,
                       generar_vencimientos=True, id_empresa=None) -> int | None:
    """Crea la financiacion, persiste el cuadro de amortizacion y (opcional) genera vencimientos AP."""
    eid = _emp(id_empresa)
    if tipo not in TIPOS:
        raise ValueError(f"tipo invalido: {tipo}")
    cuadro = cuadro_amortizacion(capital, tipo_interes_anual, num_cuotas, periodicidad=periodicidad,
                                 fecha_inicio=fecha_inicio, valor_residual=valor_residual)
    cuota = cuadro[0]["cuota"] if cuadro else 0
    fecha_fin = cuadro[-1]["fecha"] if cuadro else None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO financiaciones (id_empresa, tipo, codigo, entidad, capital, tipo_interes, "
                        "periodicidad, num_cuotas, cuota, saldo_pendiente, valor_residual, fecha_inicio, "
                        "fecha_fin, id_cuenta) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, tipo, codigo, entidad, capital, tipo_interes_anual, periodicidad, num_cuotas,
                         cuota, capital, valor_residual, fecha_inicio, fecha_fin, id_cuenta))
            fid = cur.lastrowid
            if not codigo:
                cur.execute("UPDATE financiaciones SET codigo=%s WHERE id=%s", (f"FIN{fid:05d}", fid))
            for c in cuadro:
                cur.execute("INSERT INTO financiacion_cuotas (id_empresa, id_financiacion, numero, fecha, cuota, "
                            "interes, principal, saldo_vivo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (eid, fid, c["numero"], c["fecha"], c["cuota"], c["interes"], c["principal"],
                             c["saldo_vivo"]))
            conn.commit()
        if generar_vencimientos:
            _generar_vencimientos(fid, cuadro, entidad, eid)
        log_auditoria("finanzas", "FIN_FINANCIACION_CREADA", "financiaciones", f"fin={fid} {tipo} {capital}")
        return fid
    except ValueError:
        raise
    except Exception as e:
        logger.error("crear_financiacion: %s", e)
        return None


def _generar_vencimientos(fid, cuadro, entidad, eid):
    """Crea un vencimiento PAGO en tesoreria por cada cuota (reutiliza db/vencimientos)."""
    try:
        from src.db import vencimientos
        with obtener_conexion() as conn, conn.cursor() as cur:
            for c in cuadro:
                vid = vencimientos.crear_vencimiento("PAGO", c["cuota"], c["fecha"], origen="financiacion",
                                                     id_documento=f"FIN:{fid}:{c['numero']}", tercero=entidad,
                                                     concepto=f"Cuota {c['numero']} financiacion {fid}",
                                                     id_empresa=eid)
                cur.execute("UPDATE financiacion_cuotas SET id_vencimiento=%s WHERE id_financiacion=%s "
                            "AND numero=%s", (vid, fid, c["numero"]))
            conn.commit()
    except Exception as e:
        logger.error("_generar_vencimientos: %s", e)


def registrar_pago_cuota(id_financiacion, numero, *, id_empresa=None) -> dict:
    """Marca una cuota como pagada y reduce el saldo pendiente de la financiacion."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT principal, estado FROM financiacion_cuotas WHERE id_financiacion=%s AND numero=%s",
                        (id_financiacion, numero))
            r = cur.fetchone()
            if not r:
                return {"ok": False, "error": "cuota inexistente"}
            r = list(r.values()) if isinstance(r, dict) else r
            if r[1] == "pagada":
                return {"ok": True, "ya_pagada": True}
            principal = float(r[0] or 0)
            cur.execute("UPDATE financiacion_cuotas SET estado='pagada' WHERE id_financiacion=%s AND numero=%s",
                        (id_financiacion, numero))
            cur.execute("UPDATE financiaciones SET saldo_pendiente=GREATEST(0, saldo_pendiente-%s) WHERE id=%s",
                        (principal, id_financiacion))
            cur.execute("SELECT saldo_pendiente FROM financiaciones WHERE id=%s", (id_financiacion,))
            sp = cur.fetchone()
            saldo = float((sp[0] if not isinstance(sp, dict) else list(sp.values())[0]) or 0)
            if saldo <= 0.01:
                cur.execute("UPDATE financiaciones SET estado='cancelada' WHERE id=%s", (id_financiacion,))
            conn.commit()
        log_auditoria("finanzas", "FIN_CUOTA_PAGADA", "financiacion_cuotas", f"fin={id_financiacion} c{numero}")
        return {"ok": True, "saldo_pendiente": saldo}
    except Exception as e:
        logger.error("registrar_pago_cuota: %s", e)
        return {"ok": False, "error": str(e)}


def cuadro(id_financiacion) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM financiacion_cuotas WHERE id_financiacion=%s ORDER BY numero", (id_financiacion,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("cuadro: %s", e)
        return []


def deuda_viva(*, id_empresa=None) -> dict:
    """Saldo pendiente total y por tipo (para BI/ratios de endeudamiento)."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT tipo, COALESCE(SUM(saldo_pendiente),0) FROM financiaciones WHERE id_empresa=%s "
                        "AND estado='vigente' GROUP BY tipo", (eid,))
            por_tipo = {(r[0] if not isinstance(r, dict) else list(r.values())[0]):
                        round(float(r[1] if not isinstance(r, dict) else list(r.values())[1]), 2)
                        for r in cur.fetchall()}
        return {"total": round(sum(por_tipo.values()), 2), "por_tipo": por_tipo}
    except Exception as e:
        logger.error("deuda_viva: %s", e)
        return {"total": 0, "por_tipo": {}}


def listar(*, tipo=None, estado=None, id_empresa=None) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM financiaciones WHERE id_empresa=%s"
    p = [eid]
    if tipo:
        q += " AND tipo=%s"; p.append(tipo)
    if estado:
        q += " AND estado=%s"; p.append(estado)
    q += " ORDER BY fecha_inicio DESC"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar financiacion: %s", e)
        return []
