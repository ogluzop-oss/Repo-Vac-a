"""
FASE G — Anomalias y alertas corporativas. Detecta sobre el DW (series de dw_hechos) y los modulos:
caidas de ventas, exceso/rotura de stock, gasto anomalo, absentismo, clientes/proveedores de riesgo,
tickets fuera de SLA, incremento de mermas/averias. Emite alertas (notificaciones) + auditoria.
Reglas explicables (variacion porcentual / umbrales / desviacion).
"""

import logging
from src.services.bi_corp import olap
from src.db.conexion import log_auditoria
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("bi_corp.alertas")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _ultimos_periodos(dominio, metrica, eid, n=6):
    filas = olap.cubo(dimensiones=("periodo",), filtros={"dominio": dominio, "metrica": metrica},
                      agregacion="sum", id_empresa=eid, limite=n)
    return sorted([(f["periodo"], float(f["valor"])) for f in filas], key=lambda x: x[0])


def _variacion_brusca(serie, *, caida=True, umbral_pct=20):
    """Detecta caida/subida brusca del ultimo periodo vs media de los anteriores."""
    if len(serie) < 3:
        return None
    vals = [v for _, v in serie]
    previos = vals[:-1]
    media = sum(previos) / len(previos)
    if media == 0:
        return None
    var = (vals[-1] - media) * 100 / abs(media)
    if caida and var <= -umbral_pct:
        return round(var, 2)
    if not caida and var >= umbral_pct:
        return round(var, 2)
    return None


def detectar(*, id_empresa=None) -> list:
    """Ejecuta todas las reglas de alerta y devuelve la lista de hallazgos (no persiste)."""
    eid = _emp(id_empresa)
    alertas = []

    def _add(tipo, severidad, mensaje, valor=None):
        alertas.append({"tipo": tipo, "severidad": severidad, "mensaje": mensaje, "valor": valor})

    # Caida de ventas
    v = _variacion_brusca(_ultimos_periodos("ventas", "facturacion", eid), caida=True)
    if v is not None:
        _add("caida_ventas", "alta", f"Facturacion cae {v}% vs media reciente", v)
    # Gasto anomalo (compras)
    g = _variacion_brusca(_ultimos_periodos("compras", "gasto_total", eid), caida=False, umbral_pct=30)
    if g is not None:
        _add("gasto_anomalo", "alta", f"Gasto en compras sube {g}% vs media", g)
    # Exceso / rotura de stock
    rot = _ultimos_periodos("stock", "roturas", eid)
    if rot and rot[-1][1] > 0:
        _add("rotura_stock", "alta", f"{int(rot[-1][1])} roturas de stock en el ultimo periodo", rot[-1][1])
    exc = _variacion_brusca(_ultimos_periodos("stock", "valor", eid), caida=False, umbral_pct=40)
    if exc is not None:
        _add("exceso_stock", "media", f"Valor de inventario sube {exc}%", exc)
    # Incremento mermas (calidad) / averias (gmao)
    mer = _variacion_brusca(_ultimos_periodos("calidad", "unidades_rechazadas", eid), caida=False, umbral_pct=25)
    if mer is not None:
        _add("incremento_mermas", "media", f"Rechazos de calidad suben {mer}%", mer)
    ave = _variacion_brusca(_ultimos_periodos("gmao", "averias_correctivas", eid), caida=False, umbral_pct=25)
    if ave is not None:
        _add("incremento_averias", "media", f"Averias correctivas suben {ave}%", ave)
    # Tickets fuera de SLA
    try:
        from src.services.sat import analitica as sat_an
        ksat = sat_an.kpis(id_empresa=eid)
        if ksat.get("cumplimiento_sla_pct", 100) < 90:
            _add("tickets_fuera_sla", "alta", f"Cumplimiento SLA {ksat.get('cumplimiento_sla_pct')}%",
                 ksat.get("cumplimiento_sla_pct"))
    except Exception:
        pass
    # Clientes de riesgo (crédito/IA financiera)
    try:
        from src.services.finanzas import ia as fin_ia
        impagos = fin_ia.prediccion_impagos(id_empresa=eid)
        if impagos:
            _add("clientes_riesgo", "alta", f"{len(impagos)} clientes con riesgo de impago", len(impagos))
    except Exception:
        pass
    # Proveedores de riesgo (evaluacion)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM proveedores_evaluacion WHERE id_empresa=%s AND calidad < 50", (eid,))
            r = cur.fetchone()
            n = (r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0
            if n:
                _add("proveedores_riesgo", "media", f"{n} proveedores con baja calidad", n)
    except Exception:
        pass

    if alertas:
        log_auditoria("bi_corp", "BI_ALERTAS", "dw_hechos", f"n={len(alertas)}")
    return alertas


def emitir_alertas(*, id_empresa=None) -> dict:
    """Detecta y notifica las alertas criticas/altas a direccion."""
    eid = _emp(id_empresa)
    alertas = detectar(id_empresa=eid)
    emitidas = 0
    try:
        from src.services import notificaciones
        for a in alertas:
            if a["severidad"] in ("alta", "critica"):
                notificaciones.emitir("bi", f"Alerta BI: {a['tipo']}", a["mensaje"], modulo="bi_corp",
                                      prioridad="alta", roles=["GERENTE", "ADMINISTRADOR"], id_empresa=eid)
                emitidas += 1
    except Exception as e:
        logger.debug("emitir_alertas: %s", e)
    return {"detectadas": len(alertas), "emitidas": emitidas, "alertas": alertas}


def _job_alertas(id_empresa):
    return f"alertas={emitir_alertas(id_empresa=id_empresa)['emitidas']}"


def registrar_jobs_alertas(id_empresa=None):
    from src.services import scheduler
    scheduler.registrar("bi_corp_alertas", _job_alertas)
    scheduler.registrar_job("bi_corp_alertas", intervalo_horas=24, descripcion="Alertas inteligentes BI",
                            id_empresa=id_empresa)
