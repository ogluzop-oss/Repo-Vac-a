"""
Puente contable de la COMISIÓN de la plataforma (F4 — Marketplace + Pagos).

En el modelo de marketplace, Smart Manager NO es dueño del principal (los fondos del comprador van al
vendedor a través del PSP). Lo único que es INGRESO de la plataforma es la **comisión** (application_fee).
Este módulo contabiliza SOLO esa comisión, al liberarse los fondos (FUNDS_RELEASED), reutilizando el motor
contable de doble partida (`services.contabilidad.asientos`) — nada de contabilidad paralela.

Asiento (comisión tratada como PVP, IVA incluido; tipo de la empresa):
    Debe  440 (Deudores — el PSP nos liquidará)      total
    Haber 705 (Prestaciones de servicios)            base
    Haber 477 (IVA repercutido)                      cuota

Idempotente (por `ref_origen = lonja_comision_<tx>`) y degradable: si la contabilidad no está disponible,
NO bloquea la liberación de fondos (el movimiento queda igualmente en el ledger inmutable `pagos_eventos`).
Las cuentas son parametrizables por empresa vía `contab_mapeo` (claves `comision_marketplace`/`deudor_psp`).
"""

import datetime as _dt
import logging

logger = logging.getLogger("pagos_marketplace.contabilizacion")


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def contabilizar_comision(id_transaccion, id_empresa=None) -> dict:
    """Contabiliza la comisión de una transacción liberada. Idempotente y degradable."""
    from src.services.lonja._common import _uno
    with _conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, id_empresa, comision_importe, divisa, asiento_comision "
                    "FROM lonja_transacciones WHERE id=%s", (id_transaccion,))
        t = _uno(cur)
    if not t:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    if t.get("asiento_comision"):
        return {"ok": True, "idempotente": True, "asiento": t["asiento_comision"]}
    comision = float(t.get("comision_importe") or 0)
    if comision <= 0:
        return {"ok": True, "sin_comision": True}

    emp = id_empresa or t["id_empresa"]
    try:
        from src.services.contabilidad import asientos as A, mapeo as M
        from src.utils.fiscalidad import desglose_iva
    except Exception as e:
        logger.info("contabilizar_comision: contabilidad no disponible (%s)", e)
        return {"ok": False, "degradado": True, "error": "contabilidad_no_disponible"}

    d = desglose_iva(comision, id_empresa=emp)
    cta_deudor = M.cuenta("deudor_psp", id_empresa=emp) or "440"
    cta_ingreso = M.cuenta("comision_marketplace", id_empresa=emp) or "705"
    cta_iva = M.cuenta("iva_rep", id_empresa=emp) or "477"
    lineas = [{"codigo_cuenta": cta_deudor, "debe": d["total"],
               "descripcion": f"Comisión Lonja tx {id_transaccion}"},
              {"codigo_cuenta": cta_ingreso, "haber": d["base"],
               "descripcion": "Comisión marketplace"}]
    if d["cuota"] > 0:
        lineas.append({"codigo_cuenta": cta_iva, "haber": d["cuota"],
                       "descripcion": "IVA repercutido comisión"})

    try:
        r = A.crear_asiento(_dt.date.today(), lineas, concepto=f"Comisión Lonja tx {id_transaccion}",
                            origen="lonja_comision", ref_origen=f"lonja_comision_{id_transaccion}",
                            idempotente=True, id_empresa=emp)
    except Exception as e:
        logger.warning("contabilizar_comision crear_asiento: %s", e)
        return {"ok": False, "degradado": True, "error": str(e)[:120]}
    if not r:
        return {"ok": False, "error": "asiento_no_creado"}

    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE lonja_transacciones SET asiento_comision=%s WHERE id=%s AND "
                        "asiento_comision IS NULL", (r["id"], id_transaccion))
            c.commit()
    except Exception as e:
        logger.debug("enlazar asiento_comision: %s", e)
    return {"ok": True, "asiento": r["id"], "base": d["base"], "cuota": d["cuota"], "total": d["total"]}
