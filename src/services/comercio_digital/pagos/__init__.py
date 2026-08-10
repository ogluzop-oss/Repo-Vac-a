"""
PCD · Pasarelas de Pago (Etapa B · Fase B6).

Orquesta el cobro de una Transacción Comercial REUTILIZANDO la pasarela existente
(`capabilities.pagos`: stripe/paypal/redsys/simulado, provider-agnostic) — NO crea una pasarela nueva.
Cadena: Dominio → Adaptador(pasarela) → Servicio externo. Las credenciales vienen de `cd_conexiones`
(cifradas, Fase B1); nunca en código. Degradable: sin proveedor/credenciales → 'simulado'.

Al confirmarse el pago, la Transacción pasa a PAGADA (las reservas siguen siendo el único bloqueo del
ATP; el stock lo mueve la política única en el cumplimiento). Webhooks firmados y deduplicados.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("cd.pagos")

FASE = "B6"


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
def _pasarela(proveedor, moneda, id_empresa):
    """Resuelve la pasarela (provider-agnostic) con credenciales de la conexión. Degradable→simulado."""
    config = {"proveedor": proveedor or "simulado", "moneda": moneda}
    try:
        from src.services.comercio_digital import conexiones
        conf = conexiones.obtener(proveedor, id_empresa=id_empresa) if proveedor else None
        if conf:
            config["modo"] = (conf.get("config") or {}).get("modo", "test")
            config.update(conexiones.credenciales(proveedor, id_empresa=id_empresa) or {})
    except Exception as e:
        logger.debug("conexion pago (%s): %s", proveedor, e)
    try:
        from src.platform import capabilities as cap
        pagos = cap.pagos()
        if pagos is not None and hasattr(pagos, "pasarela_para"):
            return pagos.pasarela_para(config)
    except Exception as e:
        logger.error("pasarela(%s): %s", proveedor, e)
    return None


def _importe(tx):
    meta = tx.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    if isinstance(meta, dict) and meta.get("total_cotizado") is not None:
        return float(meta["total_cotizado"])
    return float(tx.get("total") or 0)


def iniciar(id_tx, *, proveedor=None, id_empresa=None, actor=None):
    """Inicia el cobro de una Transacción: crea el cobro en la pasarela y registra el intento. Devuelve
    {ok, referencia, url, estado}. No cobra de verdad en 'simulado'."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital import transacciones
    tx = transacciones.obtener(id_tx, emp)
    if not tx:
        return {"ok": False, "motivo": "transacción no encontrada"}
    importe, moneda = _importe(tx), (tx.get("moneda") or "EUR")
    gw = _pasarela(proveedor, moneda, emp)
    if gw is None:
        return {"ok": False, "motivo": "pasarela no disponible"}
    prov = getattr(gw, "nombre", proveedor or "simulado")
    try:
        res = gw.crear_cobro({"total": importe, "moneda": moneda, "referencia": id_tx,
                              "concepto": f"Pedido {id_tx}"})
    except Exception as e:
        logger.error("crear_cobro(%s): %s", id_tx, e)
        res = {"ok": False, "mensaje": str(e)}
    ref = res.get("referencia") or ""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO cd_pagos (id_empresa, id_tx, proveedor, referencia_externa, "
                        "importe, moneda, estado, url_pago, actor) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_tx, prov, ref, importe, moneda,
                         "iniciado" if res.get("ok") else "fallido", res.get("url"), actor))
            conn.commit()
    except Exception as e:
        logger.error("registrar pago(%s): %s", id_tx, e)
    return {"ok": bool(res.get("ok")), "referencia": ref, "url": res.get("url"),
            "estado": res.get("estado", "pendiente"), "proveedor": prov, "importe": importe}


def confirmar(id_tx, *, referencia=None, id_empresa=None, actor=None, verificar=True):
    """Confirma el pago: (opcional) verifica con la pasarela, marca el pago pagado y pasa la
    Transacción a PAGADA. Idempotente (si ya está PAGADA/pagado, no repite)."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital import transacciones
    fila = _pago(id_tx, emp, referencia)
    if not fila:
        return {"ok": False, "motivo": "pago no encontrado"}
    if fila["estado"] == "pagado":
        return {"ok": True, "estado": "PAGADA", "idempotente": True}
    if verificar:
        gw = _pasarela(fila.get("proveedor"), fila.get("moneda") or "EUR", emp)
        estado_pasarela = gw.verificar_pago(fila.get("referencia_externa")) if gw else "pagado"
        if estado_pasarela != "pagado":
            _actualizar_estado(fila["id"], "fallido" if estado_pasarela == "fallido" else "iniciado")
            return {"ok": False, "motivo": f"pago {estado_pasarela}"}
    _actualizar_estado(fila["id"], "pagado")
    res = transacciones.transicionar(id_tx, "PAGADA", actor=actor or "pagos", id_empresa=emp)
    return {"ok": bool(res.get("ok")), "estado": res.get("hasta") if res.get("ok") else None,
            "tx": res}


def cobrar_express(id_tx, *, proveedor=None, id_empresa=None, actor=None):
    """Cobro en 1 CLIC: orquesta `iniciar` + `confirmar` en una sola llamada, SIN motor nuevo (N7).

    Honestidad de producción:
      • En 'simulado' (sin proveedor/credenciales reales) el cobro se AUTO-CONFIRMA → Transacción PAGADA,
        marcando `simulado=True` (jamás se presenta como un cobro real).
      • Con una pasarela REAL, NO se auto-confirma: se devuelve `pendiente=True` + `url`/`referencia`; el
        pago sólo pasa a PAGADA cuando llega el webhook firmado de la pasarela (`webhook`/`confirmar`).
    Devuelve un dict unificado {ok, estado, simulado|pendiente, referencia, url, proveedor, importe}.
    """
    emp = _emp(id_empresa)
    if estado(id_tx, id_empresa=emp) == "pagado":               # ya cobrado → no crea otro intento
        return {"ok": True, "estado": "PAGADA", "idempotente": True}
    ini = iniciar(id_tx, proveedor=proveedor, id_empresa=emp, actor=actor)
    if not ini.get("ok"):
        return {"ok": False, "motivo": ini.get("motivo", "no se pudo iniciar el cobro"), **ini}
    es_simulado = (ini.get("proveedor") or "simulado") == "simulado"
    if not es_simulado:
        # Pasarela real: el cobro queda pendiente de confirmación por webhook (no se inventa 'pagado').
        return {"ok": True, "pendiente": True, "estado": ini.get("estado", "pendiente"),
                "referencia": ini.get("referencia"), "url": ini.get("url"),
                "proveedor": ini.get("proveedor"), "importe": ini.get("importe")}
    conf = confirmar(id_tx, referencia=ini.get("referencia"), id_empresa=emp, actor=actor,
                     verificar=False)
    return {"ok": bool(conf.get("ok")), "simulado": True, "estado": conf.get("estado"),
            "referencia": ini.get("referencia"), "proveedor": ini.get("proveedor"),
            "importe": ini.get("importe"), "confirmacion": conf}


def webhook(proveedor, payload, *, firma=None, cuerpo_raw=None, event_id=None, id_empresa=None):
    """Procesa un webhook de pago: verifica firma (HMAC), deduplica por event_id y confirma la
    Transacción asociada. Firma inválida → rechazo; degradable si no hay secreto."""
    emp = _emp(id_empresa)
    verificado = None
    if firma:
        verificado = _verificar_firma(proveedor, cuerpo_raw if cuerpo_raw is not None else payload,
                                      firma, emp)
        if verificado is False:
            return {"ok": False, "motivo": "firma inválida"}
    ev = str(event_id or (payload or {}).get("id") or "")
    if ev and _webhook_visto(emp, proveedor, ev):
        return {"ok": True, "duplicado": True}
    ref = (payload or {}).get("referencia") or (payload or {}).get("reference")
    fila = _pago_por_referencia(emp, ref) if ref else None
    if not fila:
        return {"ok": False, "motivo": "pago no encontrado para la referencia"}
    if ev:
        _marcar_webhook(fila["id"], ev)
    estado = (payload or {}).get("estado") or "pagado"
    if estado == "pagado":
        return confirmar(fila["id_tx"], referencia=fila["referencia_externa"], id_empresa=emp,
                         verificar=False)
    _actualizar_estado(fila["id"], "fallido")
    return {"ok": False, "estado": estado}


def estado(id_tx, *, id_empresa=None):
    fila = _pago(id_tx, _emp(id_empresa), None)
    return fila.get("estado") if fila else None


def refund(id_tx, *, id_empresa=None, actor=None, motivo=None, evento="CommerceRefunded"):
    """Reembolso PROVIDER-AGNOSTIC: localiza el pago de la Transacción y delega el reembolso en la MISMA
    pasarela que cobró (si expone `reembolsar`); si no, lo REGISTRA (degradable, sin lógica bancaria).
    Marca el pago 'reembolsado', publica `evento` en el Event Bus y audita. Idempotente. Reutiliza la
    pasarela existente (`capabilities.pagos`); nunca implementa lógica bancaria."""
    emp = _emp(id_empresa)
    fila = _pago(id_tx, emp, None)
    if not fila:
        return {"ok": False, "motivo": "pago no encontrado"}
    if fila.get("estado") == "reembolsado":
        return {"ok": True, "estado": "reembolsado", "idempotente": True}
    importe = fila.get("importe")
    proveedor = fila.get("proveedor")
    via = "registrado"
    try:
        gw = _pasarela(proveedor, fila.get("moneda") or "EUR", emp)
        if gw is not None and hasattr(gw, "reembolsar"):
            via = "pasarela" if gw.reembolsar(fila.get("referencia_externa"), importe) else "registrado"
    except Exception as e:
        logger.debug("refund pasarela (%s): %s", id_tx, e)
    _actualizar_estado(fila["id"], "reembolsado")
    try:
        eb = cap.eventbus()
        if eb is not None:
            eb.publish(evento, id_empresa=emp, ref_entidad="transaccion", ref_id=id_tx,
                       payload={"importe": float(importe or 0), "proveedor": proveedor,
                                "motivo": motivo, "via": via})
    except Exception as e:
        logger.debug("refund evento (%s): %s", id_tx, e)
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("comercio_digital", "REFUND", "cd_pagos",
                      f"tx={id_tx} importe={importe} via={via} motivo={motivo or ''}"[:255])
    except Exception:
        pass
    return {"ok": True, "estado": "reembolsado", "importe": float(importe or 0), "via": via}


# ── helpers de BD (ledger de pagos) ───────────────────────────────────────────
_COLS = ("id", "id_tx", "proveedor", "referencia_externa", "importe", "moneda", "estado")
_SEL = "id, id_tx, proveedor, referencia_externa, importe, moneda, estado"


def _fila(cur):
    r = cur.fetchone()
    if not r:
        return None
    return r if isinstance(r, dict) else dict(zip(_COLS, r))


def _pago(id_tx, emp, referencia):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if referencia:
                cur.execute(f"SELECT {_SEL} FROM cd_pagos WHERE id_empresa=%s AND id_tx=%s AND "
                            "referencia_externa=%s ORDER BY id DESC LIMIT 1", (emp, id_tx, referencia))
            else:
                cur.execute(f"SELECT {_SEL} FROM cd_pagos WHERE id_empresa=%s AND id_tx=%s "
                            "ORDER BY id DESC LIMIT 1", (emp, id_tx))
            return _fila(cur)
    except Exception as e:
        logger.error("_pago(%s): %s", id_tx, e)
        return None


def _pago_por_referencia(emp, referencia):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_SEL} FROM cd_pagos WHERE id_empresa=%s AND referencia_externa=%s "
                        "ORDER BY id DESC LIMIT 1", (emp, referencia))
            return _fila(cur)
    except Exception:
        return None


def _actualizar_estado(id_pago, estado):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cd_pagos SET estado=%s, ts_actualizado=%s WHERE id=%s",
                        (estado, datetime.now(), id_pago))
            conn.commit()
    except Exception as e:
        logger.error("_actualizar_estado(%s): %s", id_pago, e)


def _marcar_webhook(id_pago, event_id):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cd_pagos SET webhook_event_id=%s WHERE id=%s", (event_id, id_pago))
            conn.commit()
    except Exception:
        pass


def _webhook_visto(emp, proveedor, event_id):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM cd_pagos WHERE id_empresa=%s AND proveedor=%s AND "
                        "webhook_event_id=%s LIMIT 1", (emp, proveedor, event_id))
            return cur.fetchone() is not None
    except Exception:
        return False


def _verificar_firma(proveedor, cuerpo, firma, id_empresa):
    """Verifica la firma HMAC del webhook de pago con el secreto de la conexión. Delega en `_base`."""
    from src.services.comercio_digital import _base
    return _base.verificar_firma_webhook(proveedor, cuerpo, firma, id_empresa)


def descriptor() -> dict:
    return {"servicio": "cd_pagos", "etapa": "B", "fase": FASE, "estado": "implementado",
            "reutiliza": ["pagos (tpv)", "conexiones", "transacciones"], "crea_pasarela_nueva": False,
            "provider_agnostic": True, "mueve_stock": False, "credenciales_en_codigo": False}


__all__ = ["FASE", "iniciar", "confirmar", "cobrar_express", "webhook", "estado", "refund", "descriptor"]
