"""
Conector HTTP webhook (Slack / Telegram / Teams por incoming-webhook) — FASE COM-10.

Envía un mensaje de texto a una URL de webhook entrante. Transporte inyectable para pruebas.
Audita la ejecución. No depende de `requests` salvo en el envío real.
"""

import json
import logging

logger = logging.getLogger("integraciones.http_webhook")


def _post(url, cuerpo_bytes, headers):
    try:
        import requests
        r = requests.post(url, data=cuerpo_bytes, headers=headers, timeout=10)
        return r.status_code
    except Exception as e:
        logger.info("http_webhook post: %s", e)
        return None


def enviar_webhook(url, mensaje, *, transport=None) -> dict:
    if not url:
        return {"ok": False, "estado": "sin_url"}
    transport = transport or _post
    cuerpo = json.dumps({"text": mensaje}, ensure_ascii=False).encode("utf-8")
    codigo = transport(url, cuerpo, {"Content-Type": "application/json"})
    ok = bool(codigo and 200 <= int(codigo) < 300)
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("sistema", "INTEGRACION_EJECUTADA", "integraciones", f"webhook http={codigo}")
    except Exception:
        pass
    return {"ok": ok, "estado": "enviado" if ok else "error", "codigo": codigo}
