"""
Facturación de uso de voz (Fase B — facturación SEPARADA del coste de voz, sobre la fundación de
Fase A en `services/voz_control_uso.py`). Copia casi exacta de `services/saas/facturacion_ia.py`
(mismo patrón estructural), adaptada a la tabla de origen (`voice_usage_logs`) y a la columna que
se factura.

Cobra a cada empresa el IMPORTE YA CON MARGEN de sus síntesis reales de ElevenLabs
(`voice_usage_logs.billed_amount_usd` — NO `cost_basis_usd`, el coste base del proveedor; lo que
se factura es el precio de REVENTA) en una factura DISTINTA de la cuota fija de suscripción y del
uso de IA (`facturas_saas.concepto='voz_uso'`, migración 0285) — nunca fusionada en la misma
línea/importe. N7: reutiliza el MISMO mecanismo de cobro que la renovación de suscripciones y la
facturación de IA (`suscripciones.emitir_factura_y_cobrar` → `BillingProvider.cobrar`), sin crear
un segundo proveedor de pago paralelo.

Cadencia e idempotencia: se factura por PERÍODOS ACUMULATIVOS, registrados en
`voz_facturacion_periodos` (copia exacta de `ia_facturacion_periodos`, independiente del ciclo de
facturación de IA). Cada corrida de `facturar_uso_voz_empresa` suma
`voice_usage_logs.billed_amount_usd` de la empresa desde el `periodo_hasta` de su ÚLTIMA fila en
`voz_facturacion_periodos` (o desde el origen de sus logs si no tiene ninguna) hasta el `hasta`
dado (por defecto: ahora mismo, UTC) — el rango es (periodo_desde, periodo_hasta] respecto a la
fila anterior, así el mismo log NUNCA se cuenta ni se cobra dos veces. Si el acumulado no alcanza
`UMBRAL_MINIMO_USD` (evita facturas de $0.00/ruido), NO se genera factura NI se avanza el
período — el importe sigue "pendiente" y se arrastra íntegro a la próxima corrida.

Cadencia recomendada: mensual, igual que `facturacion_ia` — mecanismo independiente
(`scheduler._job_voz_facturacion` → `voz_facturacion`, mismo patrón opt-in).
"""

import datetime as _dt
import logging

from src.db.conexion import obtener_conexion
from src.services.saas import suscripciones as _S

logger = logging.getLogger("saas.facturacion_voz")

# Umbral mínimo (USD) para generar una factura de uso de voz: evita facturas de "$0.00" o de
# fracciones de céntimo por ruido. Lo que quede por debajo NO se pierde: se arrastra (no se avanza
# `periodo_hasta`) hasta que el acumulado lo supere. Mismo valor que `facturacion_ia`.
UMBRAL_MINIMO_USD = 0.01


def _ultimo_periodo_hasta(id_empresa):
    """`periodo_hasta` de la última fila ya facturada de esta empresa, o None si nunca se facturó
    (en cuyo caso se cuenta desde el primer log existente)."""
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT periodo_hasta FROM voz_facturacion_periodos WHERE id_empresa=%s "
                    "ORDER BY id DESC LIMIT 1", (id_empresa,))
        r = cur.fetchone()
        if not r:
            return None
        return r[0] if not isinstance(r, dict) else r["periodo_hasta"]


def _empresas_con_uso_voz() -> list:
    """Empresas con al menos un registro en `voice_usage_logs` (candidatas a facturación de uso
    de voz cuando se factura "todas"), mismo criterio que `facturacion_ia._empresas_con_uso_ia`."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT id_empresa FROM voice_usage_logs")
            return [r[0] if not isinstance(r, dict) else r["id_empresa"] for r in cur.fetchall()]
    except Exception as e:
        logger.error("_empresas_con_uso_voz: %s", e)
        return []


def _acumulado_pendiente(id_empresa, desde, hasta):
    """(importe_acumulado_sin_redondear, periodo_desde_real) del uso de voz FACTURABLE
    (`billed_amount_usd`, con margen) de la empresa en el rango (desde, hasta] — o
    (None, hasta] si `desde` es None (nunca facturada antes: se cuenta desde el primer log
    existente, que pasa a ser el `periodo_desde` real de esta factura)."""
    with obtener_conexion() as conn, conn.cursor() as cur:
        if desde:
            cur.execute("SELECT COALESCE(SUM(billed_amount_usd),0) AS total, MIN(creado) AS primero "
                        "FROM voice_usage_logs WHERE id_empresa=%s AND creado>%s AND creado<=%s",
                        (id_empresa, desde, hasta))
        else:
            cur.execute("SELECT COALESCE(SUM(billed_amount_usd),0) AS total, MIN(creado) AS primero "
                        "FROM voice_usage_logs WHERE id_empresa=%s AND creado<=%s", (id_empresa, hasta))
        fila = cur.fetchone()
        total, primero = (fila["total"], fila["primero"]) if isinstance(fila, dict) else (fila[0], fila[1])
        return float(total or 0), (primero or desde)


def facturar_uso_voz_empresa(id_empresa, hasta=None) -> dict:
    """Factura el uso de voz acumulado y PENDIENTE (importe YA con margen) de UNA empresa.
    Devuelve {facturado: True, importe, numero, estado_pago, id_factura} si se emitió factura, o
    {facturado: False, importe: 0.0, motivo} si el acumulado no llegó al umbral mínimo."""
    hasta = hasta or _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    desde = _ultimo_periodo_hasta(id_empresa)
    importe_pendiente, periodo_desde = _acumulado_pendiente(id_empresa, desde, hasta)
    if importe_pendiente < UMBRAL_MINIMO_USD:
        return {"facturado": False, "importe": 0.0, "motivo": "sin uso de voz o por debajo del umbral"}

    importe = round(importe_pendiente, 2)   # redondeo SOLO al facturar; los logs conservan su precisión real
    s = _S.estado(id_empresa)   # suscripción actual (si existe): mismo medio de pago domiciliado
    proveedor = (s or {}).get("proveedor_pago")
    id_suscripcion = (s or {}).get("id")
    fid, numero, estado_pago = _S.emitir_factura_y_cobrar(
        id_empresa, importe, "voz_uso", id_suscripcion=id_suscripcion, proveedor=proveedor)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO voz_facturacion_periodos (id_empresa, periodo_desde, periodo_hasta, "
                    "id_factura_saas) VALUES (%s,%s,%s,%s)", (id_empresa, periodo_desde, hasta, fid))
        conn.commit()
    _audit(id_empresa, numero, importe, estado_pago)
    return {"facturado": True, "importe": importe, "numero": numero, "estado_pago": estado_pago,
            "id_factura": fid}


def facturar_uso_voz(id_empresa=None, hasta=None) -> dict:
    """Factura el uso de voz acumulado de UNA empresa (`id_empresa`) o de TODAS las que tengan
    registros en `voice_usage_logs` (`id_empresa=None`). Devuelve
    {procesadas, facturadas, omitidas, fallidas}."""
    empresas = [id_empresa] if id_empresa else _empresas_con_uso_voz()
    procesadas = facturadas = omitidas = fallidas = 0
    for emp in empresas:
        try:
            r = facturar_uso_voz_empresa(emp, hasta=hasta)
            procesadas += 1
            if r.get("facturado"):
                facturadas += 1
            else:
                omitidas += 1
        except Exception as e:
            logger.error("facturar_uso_voz(%s): %s", emp, e)
            fallidas += 1
    if procesadas:
        logger.info("Facturación de uso de voz: %s procesadas, %s facturadas, %s omitidas, %s fallidas.",
                    procesadas, facturadas, omitidas, fallidas)
    return {"procesadas": procesadas, "facturadas": facturadas, "omitidas": omitidas, "fallidas": fallidas}


def job(id_empresa=None) -> str:
    """Callable para el Scheduler (opt-in; mismo patrón que `facturacion_ia.job`). Factura el uso
    de voz acumulado de todas las empresas con actividad en `voice_usage_logs`."""
    r = facturar_uso_voz()
    return (f"facturación uso voz: procesadas={r['procesadas']} facturadas={r['facturadas']} "
            f"omitidas={r['omitidas']} fallidas={r['fallidas']}")


def _audit(id_empresa, numero, importe, estado_pago):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", "FACTURA_VOZ_USO", "facturas_saas",
                       f"{id_empresa}: factura={numero} importe={importe} estado={estado_pago}")
    except Exception:
        pass
