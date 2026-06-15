"""Interfaz común de los verificadores de webhook de pago."""

import logging

logger = logging.getLogger("pagos.webhooks.base")


def resultado(ok, estado="pendiente", referencia=None, evento_id=None,
              evento_tipo=None, mensaje="") -> dict:
    """Estructura uniforme que devuelve un verificador de webhook."""
    return {"ok": bool(ok), "estado": estado, "referencia": referencia,
            "evento_id": evento_id, "evento_tipo": evento_tipo, "mensaje": mensaje}


class VerificadorWebhook:
    """Contrato de un verificador: valida firma/autenticidad y normaliza el evento.

    `verificar(headers, body, config)` debe:
      - validar la FIRMA y la AUTENTICIDAD (sin confiar en el cuerpo a ciegas),
      - protegerse de REPLAY (tolerancia de tiempo cuando el proveedor la ofrece),
      - devolver `resultado(ok, estado, referencia, evento_id, evento_tipo, mensaje)`
        donde `referencia` localiza el pedido y `estado` ∈ pagado|fallido|pendiente.
    """

    nombre = "base"

    def verificar(self, headers: dict, body: bytes, config: dict) -> dict:
        return resultado(False, mensaje="Verificador no implementado.")
