"""
Emisor Verifactu → AEAT (C3.3.3) — adaptador de ENVÍO. Encapsula TODA la
especificidad de AEAT para no tocar el worker congelado: construye el XML, hace el
POST al web service, parsea la respuesta y PERSISTE la trazabilidad (estado/CSV) +
la EVIDENCIA del acuse. El worker solo orquesta (genérico, idempotente, backoff).

Inyección de `transporte` (callable(url, cuerpo:bytes, cfg)->(status:int, texto:str))
para poder validar el FLUJO COMPLETO en tests sin red ni certificados. En operación,
el transporte real (TLS con certificado de representante/sello) y el paso a
PRODUCCIÓN se consolidan en C3.5; por eso, sin transporte listo, `disponible()` es
False y el worker deja el registro en espera (no se envía nada a ciegas).

⚠️ endpoints, sobre SOAP y parseo de respuesta DEBEN cotejarse con el WSDL oficial
de AEAT y el entorno de preproducción antes de habilitar envíos reales.
"""

import logging
import re

from src.services.fiscal.base import Emisor

logger = logging.getLogger("fiscal.emisor.verifactu")

# Endpoints del web service Verifactu. ⚠️[verificar WSDL/URLs oficiales]
_ENDPOINT = {
    "preproduccion": "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
    "produccion": "https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
}
_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


class EmisorVerifactu(Emisor):
    nombre = "verifactu-aeat"

    def __init__(self, transporte=None, config=None):
        self._transporte = transporte          # inyectable en tests
        self.config = config or {}

    def disponible(self) -> bool:
        # Listo si hay transporte (inyectado en test) o certificado configurado (C3.5).
        return self._transporte is not None or bool(self.config.get("cert_listo"))

    def endpoint(self, config: dict) -> str:
        ent = (config or {}).get("entorno", "preproduccion")
        return _ENDPOINT.get(ent, _ENDPOINT["preproduccion"])

    def _sobre_soap(self, cuerpo_xml: str) -> bytes:
        env = (f'<soapenv:Envelope xmlns:soapenv="{_SOAP_NS}">'
               f'<soapenv:Body>{cuerpo_xml}</soapenv:Body></soapenv:Envelope>')
        return env.encode("utf-8")

    def _http(self, url: str, cuerpo: bytes, config: dict):
        """Transporte real (requests + certificado). El certificado se cablea en C3.5."""
        import requests
        cert = config.get("cert")           # (ruta_pem, ruta_key) — C3.5
        r = requests.post(url, data=cuerpo,
                          headers={"Content-Type": "text/xml; charset=utf-8"},
                          cert=cert, timeout=30)
        return r.status_code, r.text

    def enviar(self, registro, config: dict) -> dict:
        from src.db import fiscal as fdb
        from src.services.fiscal import verifactu_xml as vx
        try:
            fila = fdb.obtener_registro(registro.id) if getattr(registro, "id", None) else None
            if not fila:
                return {"ok": False, "estado": "pendiente", "mensaje": "registro no encontrado"}
            cuerpo = self._sobre_soap(vx.lote_xml([fila]))
            transporte = self._transporte or self._http
            status, texto = transporte(self.endpoint(config), cuerpo, config)
            res = self._parse(status, texto)
            # Persistencia AEAT + evidencias (responsabilidad del adaptador).
            fdb.actualizar_aeat(registro.id, estado_aeat=res.get("estado_aeat"),
                                csv_aeat=res.get("csv"))
            self._evidencias(fila, cuerpo, texto, config)
            return res
        except Exception as e:
            logger.warning("EmisorVerifactu.enviar(reg=%s): %s", getattr(registro, "id", "?"), e)
            return {"ok": False, "estado": "pendiente", "mensaje": str(e)}

    def _evidencias(self, fila, sobre: bytes, respuesta: str, config: dict):
        try:
            from src.services.fiscal.evidencias import guardar_evidencia
            guardar_evidencia(fila, "xml", sobre.decode("utf-8"),
                              id_empresa=fila.get("id_empresa"))
            if respuesta:
                guardar_evidencia(fila, "acuse", respuesta, id_empresa=fila.get("id_empresa"))
        except Exception as e:
            logger.debug("No se pudieron guardar evidencias AEAT: %s", e)

    @staticmethod
    def _parse(status: int, texto: str) -> dict:
        """Parseo del acuse AEAT. ⚠️[ajustar a los nombres reales del WSDL]."""
        texto = texto or ""
        def _busca(tag):
            m = re.search(rf"<[^>:]*:?{tag}>([^<]+)</", texto)
            return m.group(1).strip() if m else None
        estado = _busca("EstadoEnvio") or _busca("EstadoRegistro")
        csv = _busca("CSV")
        if status == 200 and (estado or "").lower() in ("correcto", "aceptadoconerrores", ""):
            return {"ok": True, "estado": "enviado", "estado_aeat": estado or "Correcto",
                    "csv": csv, "mensaje": _busca("DescripcionErrorRegistro")}
        return {"ok": False, "estado": "pendiente", "estado_aeat": estado or "Incorrecto",
                "csv": csv, "mensaje": _busca("DescripcionErrorRegistro") or f"HTTP {status}"}
