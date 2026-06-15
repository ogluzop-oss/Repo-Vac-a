"""Verificador de notificación (webhook) de Redsys.

Redsys envía Ds_MerchantParameters (base64 JSON) + Ds_Signature (HMAC-SHA256, en
base64 url-safe, sobre la clave derivada por 3DES del nº de pedido). Se valida la
firma con la clave secreta del comercio y se normaliza el resultado.
"""

import base64
import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qs

from src.services.tpv.pagos.redsys import _3des_cbc_encrypt
from src.services.tpv.pagos.webhooks.base import VerificadorWebhook, resultado
from src.services.tpv.pagos.webhooks.registry import registrar_webhook

logger = logging.getLogger("pagos.webhooks.redsys")


def _b64norm(s: str) -> str:
    return (s or "").replace("-", "+").replace("_", "/")


@registrar_webhook("redsys")
class WebhookRedsys(VerificadorWebhook):
    nombre = "redsys"

    def verificar(self, headers: dict, body: bytes, config: dict) -> dict:
        secret_b64 = (config or {}).get("api_secret") or ""
        if not secret_b64:
            return resultado(False, mensaje="Falta la clave secreta de Redsys.")
        raw = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else str(body)
        try:
            campos = {k: v[0] for k, v in parse_qs(raw).items()}
            if "Ds_MerchantParameters" not in campos:
                campos = {**campos, **(json.loads(raw) if raw.strip().startswith("{") else {})}
        except Exception:
            return resultado(False, mensaje="Cuerpo de notificación Redsys ilegible.")
        merchant_params = campos.get("Ds_MerchantParameters")
        firma_recibida = campos.get("Ds_Signature")
        if not merchant_params or not firma_recibida:
            return resultado(False, mensaje="Faltan parámetros/firma de Redsys.")
        try:
            datos = json.loads(base64.b64decode(merchant_params).decode("utf-8"))
        except Exception:
            return resultado(False, mensaje="Ds_MerchantParameters no decodificable.")
        order = datos.get("Ds_Order") or datos.get("DS_ORDER") or ""
        try:
            clave = base64.b64decode(secret_b64)
        except Exception:
            return resultado(False, mensaje="Clave secreta de Redsys inválida (base64).")
        derived = _3des_cbc_encrypt(clave, order.encode())
        if derived is None:
            return resultado(False, mensaje="Falta backend de cifrado (3DES) para verificar Redsys.")
        firma_calc = base64.b64encode(
            hmac.new(derived, merchant_params.encode(), hashlib.sha256).digest()).decode()
        if not hmac.compare_digest(_b64norm(firma_calc), _b64norm(firma_recibida)):
            return resultado(False, mensaje="Firma de Redsys no válida.")
        # Ds_Response: 0000–0099 = autorizada (pagado); resto = denegada/fallida.
        try:
            resp = int(datos.get("Ds_Response", datos.get("DS_RESPONSE", 9999)))
        except (TypeError, ValueError):
            resp = 9999
        estado = "pagado" if 0 <= resp <= 99 else "fallido"
        auth = datos.get("Ds_AuthorisationCode") or datos.get("DS_AUTHORISATIONCODE") or resp
        return resultado(True, estado=estado, referencia=order,
                         evento_id=f"{order}-{auth}", evento_tipo=f"Ds_Response:{resp}",
                         mensaje="Firma Redsys verificada.")
