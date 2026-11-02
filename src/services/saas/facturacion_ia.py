"""
Facturación de uso de IA (Fase B — facturación SEPARADA del coste de IA, sobre la fundación de
Fase A en `services/ia_control_uso.py`).

Cobra a cada empresa el coste ACUMULADO de sus llamadas reales a la API de Anthropic
(`ai_usage_logs.estimated_cost_usd`) en una factura DISTINTA de la cuota fija de suscripción
(`facturas_saas.concepto='ia_uso'` vs `'suscripcion'`, migración 0276) — nunca fusionada en la
misma línea/importe, tal como pide el negocio ("cobrar el coste por uso de la API aparte de su
tarifa mensual de suscripción"). N7: reutiliza el MISMO mecanismo de cobro que la renovación de
suscripciones (`suscripciones.emitir_factura_y_cobrar` → `BillingProvider.cobrar`), sin crear un
segundo proveedor de pago paralelo; usa el `proveedor_pago` ya domiciliado de la propia
suscripción de la empresa cuando existe (mismo medio de pago para ambos conceptos).

Cadencia e idempotencia: se factura por PERÍODOS ACUMULATIVOS, registrados en
`ia_facturacion_periodos`. Cada corrida de `facturar_uso_ia_empresa` suma
`ai_usage_logs.estimated_cost_usd` de la empresa desde el `periodo_hasta` de su ÚLTIMA fila en
`ia_facturacion_periodos` (o desde el origen de sus logs si no tiene ninguna) hasta el `hasta`
dado (por defecto: ahora mismo, UTC) — el rango es (periodo_desde, periodo_hasta] respecto a la
fila anterior, así el mismo log NUNCA se cuenta ni se cobra dos veces. Si el acumulado no alcanza
`UMBRAL_MINIMO_USD` (evita facturas de $0.00/ruido), NO se genera factura NI se avanza el
período — el coste sigue "pendiente" y se arrastra íntegro a la próxima corrida (nunca se pierde
ni se re-cuenta). El redondeo a 2 decimales ocurre SOLO al fijar el `importe` de la factura; los
`ai_usage_logs` conservan su precisión DECIMAL(10,6) intacta (nunca se tocan/marcan, la
idempotencia vive enteramente en `ia_facturacion_periodos`).

Cadencia recomendada de ejecución: mensual, alineada con el propio ciclo de renovación de la
suscripción de cada empresa — pero el mecanismo es independiente de `facturacion_automatica.py`
(que factura la cuota fija de suscripciones vencidas): un job opt-in DISTINTO
(`scheduler._job_ia_facturacion` → `ia_facturacion`, mismo patrón opt-in que `saas_facturacion`),
para no acoplar el ciclo de renovación de la suscripción con la facturación de uso de IA.
"""

import datetime as _dt
import logging

from src.db.conexion import obtener_conexion
from src.services.saas import suscripciones as _S

logger = logging.getLogger("saas.facturacion_ia")

# Umbral mínimo (USD) para generar una factura de uso de IA: evita facturas de "$0.00" o de
# fracciones de céntimo por ruido de una sola llamada barata. Lo que quede por debajo NO se
# pierde: se arrastra (no se avanza `periodo_hasta`) hasta que el acumulado lo supere.
UMBRAL_MINIMO_USD = 0.01


def _ultimo_periodo_hasta(id_empresa):
    """`periodo_hasta` de la última fila ya facturada de esta empresa, o None si nunca se facturó
    (en cuyo caso se cuenta desde el primer log existente)."""
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT periodo_hasta FROM ia_facturacion_periodos WHERE id_empresa=%s "
                    "ORDER BY id DESC LIMIT 1", (id_empresa,))
        r = cur.fetchone()
        if not r:
            return None
        return r[0] if not isinstance(r, dict) else r["periodo_hasta"]


def _empresas_con_uso_ia() -> list:
    """Empresas con al menos un registro en `ai_usage_logs` (candidatas a facturación de uso de
    IA cuando se factura "todas", mismo criterio "todas las empresas con algo que facturar" que
    `facturacion_automatica.suscripciones_vencidas`)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT id_empresa FROM ai_usage_logs")
            return [r[0] if not isinstance(r, dict) else r["id_empresa"] for r in cur.fetchall()]
    except Exception as e:
        logger.error("_empresas_con_uso_ia: %s", e)
        return []


def _acumulado_pendiente(id_empresa, desde, hasta):
    """(importe_acumulado_sin_redondear, periodo_desde_real) del uso de IA de la empresa en el
    rango (desde, hasta] — o (None, hasta] si `desde` es None (nunca facturada antes: se cuenta
    desde el primer log existente, que pasa a ser el `periodo_desde` real de esta factura)."""
    with obtener_conexion() as conn, conn.cursor() as cur:
        if desde:
            cur.execute("SELECT COALESCE(SUM(estimated_cost_usd),0) AS total, MIN(creado) AS primero "
                        "FROM ai_usage_logs WHERE id_empresa=%s AND creado>%s AND creado<=%s",
                        (id_empresa, desde, hasta))
        else:
            cur.execute("SELECT COALESCE(SUM(estimated_cost_usd),0) AS total, MIN(creado) AS primero "
                        "FROM ai_usage_logs WHERE id_empresa=%s AND creado<=%s", (id_empresa, hasta))
        fila = cur.fetchone()
        total, primero = (fila["total"], fila["primero"]) if isinstance(fila, dict) else (fila[0], fila[1])
        return float(total or 0), (primero or desde)


def facturar_uso_ia_empresa(id_empresa, hasta=None) -> dict:
    """Factura el uso de IA acumulado y PENDIENTE de UNA empresa. Devuelve
    {facturado: True, importe, numero, estado_pago, id_factura} si se emitió factura, o
    {facturado: False, importe: 0.0, motivo} si el acumulado no llegó al umbral mínimo."""
    hasta = hasta or _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    desde = _ultimo_periodo_hasta(id_empresa)
    coste, periodo_desde = _acumulado_pendiente(id_empresa, desde, hasta)
    if coste < UMBRAL_MINIMO_USD:
        return {"facturado": False, "importe": 0.0, "motivo": "sin uso de IA o por debajo del umbral"}

    importe = round(coste, 2)   # redondeo SOLO al facturar; los logs conservan su precisión real
    s = _S.estado(id_empresa)   # suscripción actual (si existe): mismo medio de pago domiciliado
    proveedor = (s or {}).get("proveedor_pago")
    id_suscripcion = (s or {}).get("id")
    fid, numero, estado_pago = _S.emitir_factura_y_cobrar(
        id_empresa, importe, "ia_uso", id_suscripcion=id_suscripcion, proveedor=proveedor)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO ia_facturacion_periodos (id_empresa, periodo_desde, periodo_hasta, "
                    "id_factura_saas) VALUES (%s,%s,%s,%s)", (id_empresa, periodo_desde, hasta, fid))
        conn.commit()
    _audit(id_empresa, numero, importe, estado_pago)
    return {"facturado": True, "importe": importe, "numero": numero, "estado_pago": estado_pago,
            "id_factura": fid}


def facturar_uso_ia(id_empresa=None, hasta=None) -> dict:
    """Factura el uso de IA acumulado de UNA empresa (`id_empresa`) o de TODAS las que tengan
    registros en `ai_usage_logs` (`id_empresa=None`). Devuelve
    {procesadas, facturadas, omitidas, fallidas}."""
    empresas = [id_empresa] if id_empresa else _empresas_con_uso_ia()
    procesadas = facturadas = omitidas = fallidas = 0
    for emp in empresas:
        try:
            r = facturar_uso_ia_empresa(emp, hasta=hasta)
            procesadas += 1
            if r.get("facturado"):
                facturadas += 1
            else:
                omitidas += 1
        except Exception as e:
            logger.error("facturar_uso_ia(%s): %s", emp, e)
            fallidas += 1
    if procesadas:
        logger.info("Facturación de uso de IA: %s procesadas, %s facturadas, %s omitidas, %s fallidas.",
                    procesadas, facturadas, omitidas, fallidas)
    return {"procesadas": procesadas, "facturadas": facturadas, "omitidas": omitidas, "fallidas": fallidas}


def job(id_empresa=None) -> str:
    """Callable para el Scheduler (opt-in; mismo patrón que `facturacion_automatica.job`). Factura
    el uso de IA acumulado de todas las empresas con actividad en `ai_usage_logs`."""
    r = facturar_uso_ia()
    return (f"facturación uso IA: procesadas={r['procesadas']} facturadas={r['facturadas']} "
            f"omitidas={r['omitidas']} fallidas={r['fallidas']}")


def _audit(id_empresa, numero, importe, estado_pago):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", "FACTURA_IA_USO", "facturas_saas",
                       f"{id_empresa}: factura={numero} importe={importe} estado={estado_pago}")
    except Exception:
        pass
