"""Pasarela Redsys (TPV virtual bancario español, cobro real).

api_secret = clave secreta del comercio (base64); comercio = código FUC;
api_key = nº de terminal (por defecto "1"). Redsys exige un POST con parámetros
firmados (HMAC-SHA256 sobre una clave derivada por 3DES del nº de pedido), por lo
que generamos un HTML autoenviable (file://) que redirige al banco al abrirlo.
Degrada con elegancia si falta un backend de cifrado (3DES).
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time

from src.services.tpv.pagos.base import PasarelaPago
from src.services.tpv.pagos.registry import registrar

logger = logging.getLogger("pagos.redsys")

_EP_TEST = "https://sis-t.redsys.es:25443/sis/realizarPago"
_EP_LIVE = "https://sis.redsys.es/sis/realizarPago"


def _3des_cbc_encrypt(clave: bytes, mensaje: bytes):
    """Cifra (3DES-CBC, IV cero, sin padding extra) el nº de pedido para derivar la
    clave de firma. Intenta `cryptography` y luego `pycryptodome`. None si falta."""
    # Redsys exige bloque múltiplo de 8 (relleno con ceros).
    if len(mensaje) % 8:
        mensaje = mensaje + b"\0" * (8 - len(mensaje) % 8)
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, modes
        try:    # cryptography >= 43: TripleDES vive en 'decrepit'
            from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
        except Exception:   # versiones anteriores
            from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES
        cipher = Cipher(TripleDES(clave), modes.CBC(b"\0" * 8))
        enc = cipher.encryptor()
        return enc.update(mensaje) + enc.finalize()
    except Exception:
        pass
    try:
        from Crypto.Cipher import DES3
        return DES3.new(clave, DES3.MODE_CBC, b"\0" * 8).encrypt(mensaje)
    except Exception:
        return None


@registrar("redsys", "Redsys", recomendada=True, orden=10)
class PasarelaRedsys(PasarelaPago):
    nombre = "redsys"

    def _endpoint(self):
        return _EP_TEST if self.es_test() else _EP_LIVE

    def _terminal(self):
        return (self.config.get("api_key") or "1").strip() or "1"

    def configurado(self) -> bool:
        return bool(self.config.get("api_secret") and self.config.get("comercio"))

    @staticmethod
    def _moneda_iso(cod):
        return {"EUR": "978", "USD": "840", "GBP": "826"}.get((cod or "EUR").upper(), "978")

    def crear_cobro(self, pedido: dict) -> dict:
        if not self.configurado():
            return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                    "mensaje": "Redsys no configurado."}
        clave = None
        try:
            clave = base64.b64decode(self.config["api_secret"])
        except Exception:
            return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                    "mensaje": "Clave secreta de Redsys inválida (base64)."}
        # Nº de pedido Redsys: 4 dígitos + alfanumérico (máx 12). Usamos timestamp.
        order = time.strftime("%H%M") + str(int(time.time()))[-6:]
        order = order[:12]
        importe = str(int(round(float(pedido.get("total") or 0) * 100)))
        params = {
            "DS_MERCHANT_AMOUNT": importe,
            "DS_MERCHANT_ORDER": order,
            "DS_MERCHANT_MERCHANTCODE": str(self.config.get("comercio") or "")[:9],
            "DS_MERCHANT_CURRENCY": self._moneda_iso(self.moneda()),
            "DS_MERCHANT_TRANSACTIONTYPE": "0",
            "DS_MERCHANT_TERMINAL": self._terminal(),
            "DS_MERCHANT_MERCHANTURL": "",
            "DS_MERCHANT_URLOK": "https://pago.local/ok",
            "DS_MERCHANT_URLKO": "https://pago.local/ko",
        }
        merchant_params = base64.b64encode(json.dumps(params).encode()).decode()
        derived = _3des_cbc_encrypt(clave, order.encode())
        if derived is None:
            return {"ok": False, "url": "", "referencia": order, "estado": "pendiente",
                    "mensaje": "Redsys requiere un backend de cifrado (cryptography/pycryptodome)."}
        firma = base64.b64encode(
            hmac.new(derived, merchant_params.encode(), hashlib.sha256).digest()).decode()
        # HTML autoenviable que hace el POST al banco al abrirse en el navegador.
        try:
            from src.utils.recursos import ruta_datos
            carpeta = ruta_datos("pagos")
        except Exception:
            carpeta = os.path.join("documentos", "pagos")
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, f"redsys_{order}.html")
        html = (
            "<!doctype html><html><head><meta charset='utf-8'></head>"
            "<body onload='document.forms[0].submit()'>"
            f"<form action='{self._endpoint()}' method='POST'>"
            "<input type='hidden' name='Ds_SignatureVersion' value='HMAC_SHA256_V1'/>"
            f"<input type='hidden' name='Ds_MerchantParameters' value='{merchant_params}'/>"
            f"<input type='hidden' name='Ds_Signature' value='{firma}'/>"
            "<noscript><button type='submit'>Pagar</button></noscript>"
            "</form></body></html>")
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception as e:
            return {"ok": False, "url": "", "referencia": order, "estado": "pendiente",
                    "mensaje": f"No se pudo preparar el formulario Redsys: {e}"}
        url = "file:///" + os.path.abspath(ruta).replace("\\", "/")
        return {"ok": True, "url": url, "referencia": order, "estado": "pendiente",
                "mensaje": "Formulario de pago Redsys preparado."}

    def verificar_pago(self, referencia: str) -> str:
        # La confirmación real de Redsys llega por notificación servidor-servidor;
        # sin webhook accesible no podemos consultarla aquí.
        return "pendiente"
