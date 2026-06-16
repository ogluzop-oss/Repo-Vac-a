"""
Worker de la cola fiscal (C3.2) — esqueleto idempotente con backoff.

Procesa los registros pendientes de firma/envío. En C3.2 el `Firmante`/`Emisor`
por defecto son NO-OP: el worker es funcional (recorre la cola, respeta el backoff,
es idempotente y reintenta), pero deja los envíos en espera hasta que C3.3/C3.4/C3.5
enchufen emisores/firmantes reales. NO contiene lógica legal ni integraciones.
"""

import datetime as _dt
import logging

logger = logging.getLogger("fiscal.worker")

MAX_INTENTOS = 8
_BACKOFF_CAP_MIN = 60          # tope del backoff exponencial (minutos)


def _backoff(intentos: int) -> _dt.datetime:
    minutos = min(2 ** max(0, intentos), _BACKOFF_CAP_MIN)
    return _dt.datetime.now() + _dt.timedelta(minutes=minutos)


def procesar_cola(id_empresa=None, limite=50, firmante=None, emisor=None) -> dict:
    """Procesa entradas listas de la cola (respeta proximo_intento). Idempotente:
    un registro ya 'enviado'/'anulado' cierra su entrada sin reenviar.

    Devuelve un resumen {enviados, en_espera, errores, vistos}."""
    from src.db import fiscal as F
    from src.services.fiscal.factory import (emisor_para, firmante_para,
                                             proveedor_para)
    res = {"enviados": 0, "en_espera": 0, "errores": 0, "vistos": 0}
    try:
        pendientes = F.listar_cola("pendiente", id_empresa=id_empresa, limite=limite, listos=True)
    except Exception as e:
        logger.error("procesar_cola/listar: %s", e)
        return res

    for item in pendientes:
        res["vistos"] += 1
        cid, rid = item["id"], item["id_registro"]
        intentos = int(item.get("intentos") or 0)
        try:
            reg = F.obtener_registro(rid)
            if not reg:
                F.actualizar_cola(cid, "error", error="registro inexistente")
                res["errores"] += 1
                continue
            # Idempotencia: ya gestionado → cerrar la entrada sin reenviar.
            if reg.get("estado") in ("enviado", "anulado"):
                F.actualizar_cola(cid, "enviado")
                res["enviados"] += 1
                continue

            cfg = F.obtener_config(reg["id_empresa"])
            fir = firmante if firmante is not None else firmante_para(cfg)
            emi = emisor if emisor is not None else emisor_para(cfg)
            from src.services.fiscal.base import RegistroFiscal
            registro = RegistroFiscal.desde_fila(reg)

            # Firma (no-op por defecto en C3.2).
            if fir.disponible():
                fir.firmar(b"")        # el payload real de firma llega en C3.5

            # Envío.
            if not emi.disponible():
                # Sin emisor configurado → espera con backoff (no es error).
                F.actualizar_cola(cid, "pendiente", error="emisor no configurado",
                                  proximo_intento=_backoff(intentos))
                res["en_espera"] += 1
                continue

            r = emi.enviar(registro, cfg)
            if r.get("ok"):
                F.actualizar_estado(rid, "enviado")
                F.actualizar_cola(cid, "enviado")
                res["enviados"] += 1
            elif intentos + 1 >= MAX_INTENTOS:
                F.actualizar_cola(cid, "error", error=r.get("mensaje") or "envío fallido")
                res["errores"] += 1
            else:
                F.actualizar_cola(cid, "pendiente", error=r.get("mensaje"),
                                  proximo_intento=_backoff(intentos))
                res["en_espera"] += 1
        except Exception as e:
            logger.warning("procesar_cola(reg=%s): %s", rid, e)
            if intentos + 1 >= MAX_INTENTOS:
                F.actualizar_cola(cid, "error", error=str(e))
                res["errores"] += 1
            else:
                F.actualizar_cola(cid, "pendiente", error=str(e),
                                  proximo_intento=_backoff(intentos))
                res["en_espera"] += 1
    return res
