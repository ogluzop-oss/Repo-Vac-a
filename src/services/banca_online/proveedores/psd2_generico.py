"""
Adaptador PSD2 genérico (Berlin Group / open banking).

Consulta GET {endpoint}/accounts/{account_id}/transactions con Bearer token y normaliza la respuesta
(estructura Berlin Group `transactions.booked[]`, o una lista simple) a
[{fecha, importe, concepto, referencia}]. Válido para la mayoría de agregadores PSD2; los conectores de
bancos concretos se añaden luego sin cambiar el resto.
"""

import json
import logging

from src.services.banca_online.proveedores.base import AdaptadorBanca

logger = logging.getLogger("banca.psd2")


class AdaptadorPSD2(AdaptadorBanca):
    codigo = "psd2_generico"

    def obtener_movimientos(self, ctx, desde, hasta, transport):
        url = f"{self._base(ctx)}/accounts/{ctx.get('account_id') or ''}/transactions"
        params = {}
        if desde:
            params["dateFrom"] = desde
        if hasta:
            params["dateTo"] = hasta
        status, texto = transport("GET", url, self._headers(ctx), params)
        if not (200 <= (status or 0) < 300):
            logger.debug("PSD2 transactions HTTP %s", status)
            return []
        try:
            data = json.loads(texto) if isinstance(texto, (str, bytes)) else texto
        except Exception:
            return []
        return self._normalizar(data)

    @staticmethod
    def _normalizar(data):
        if isinstance(data, list):
            lista = data
        else:
            data = data or {}
            tx = data.get("transactions")
            if isinstance(tx, dict):
                lista = tx.get("booked") or []
            elif isinstance(tx, list):
                lista = tx
            else:
                lista = []
        movs = []
        for t in lista or []:
            amt = t.get("transactionAmount")
            raw = amt.get("amount") if isinstance(amt, dict) else amt
            if raw in (None, ""):
                raw = t.get("amount")
            try:
                importe = round(float(raw), 2)
            except (TypeError, ValueError):
                importe = 0.0
            movs.append({
                "fecha": t.get("bookingDate") or t.get("valueDate") or t.get("fecha"),
                "importe": importe,
                "concepto": (t.get("remittanceInformationUnstructured") or t.get("concepto")
                             or t.get("description")),
                "referencia": t.get("transactionId") or t.get("endToEndId") or t.get("referencia"),
            })
        return movs
