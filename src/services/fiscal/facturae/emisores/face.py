"""
Canal FACe (B2G) (C3.4.4) — entrega de Facturae al sector público.

Reutiliza el transporte mTLS en memoria de C3.5 (`emisores/tls.py`). Transporte
inyectable para validar el flujo sin red ni certificado. El XML firmado se envía en
base64 dentro del sobre SOAP de FACe. ⚠️ El sobre/operación/parsers exactos deben
cotejarse con el WSDL oficial de FACe y el entorno de pruebas antes de producción.
"""

import base64
import logging
import xml.etree.ElementTree as ET

from src.services.fiscal.facturae.canal_base import CanalFacturae

logger = logging.getLogger("fiscal.facturae.face")

# Endpoints FACe (SSPP web service). ⚠️[verificar WSDL/URLs oficiales]
_ENDPOINT = {
    "preproduccion": "https://se-face-webservice.redsara.es/facturasspp2/services/v2",
    "produccion": "https://webservice.face.gob.es/facturasspp2/services/v2",
}
_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


def _local(t):
    return t.tag.rsplit("}", 1)[-1] if "}" in t.tag else t.tag


def _buscar(root, nombre):
    for el in root.iter():
        if _local(el) == nombre:
            return el
    return None


class CanalFACe(CanalFacturae):
    nombre = "face"

    def __init__(self, transporte=None, config=None):
        self._transporte = transporte
        self.config = config or {}

    def disponible(self) -> bool:
        return self._transporte is not None or bool(self.config.get("cert_listo"))

    def endpoint(self, config: dict) -> str:
        ent = (config or {}).get("entorno", "preproduccion")
        return _ENDPOINT.get(ent, _ENDPOINT["preproduccion"])

    def _sobre(self, xml_firmado: bytes, datos: dict) -> bytes:
        b64 = base64.b64encode(xml_firmado).decode("ascii")
        nombre = f"{datos.get('numero', 'factura')}.xsig"
        cuerpo = (f'<ns:registrarFactura xmlns:ns="https://webservice.face.gob.es">'
                  f'<factura><factura>{b64}</factura>'
                  f'<nombre>{nombre}</nombre></factura>'
                  f'</ns:registrarFactura>')
        env = (f'<soapenv:Envelope xmlns:soapenv="{_SOAP_NS}">'
               f'<soapenv:Body>{cuerpo}</soapenv:Body></soapenv:Envelope>')
        return env.encode("utf-8")

    def _http(self, url, cuerpo, config):
        import requests
        r = requests.post(url, data=cuerpo, cert=config.get("cert"),
                          headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""},
                          timeout=int(config.get("timeout", 30)))
        return r.status_code, r.text

    def enviar(self, xml_firmado: bytes, datos: dict, config: dict) -> dict:
        try:
            transporte = self._transporte or self._http
            status, texto = transporte(self.endpoint(config), self._sobre(xml_firmado, datos), config)
            return self._parse(status, texto)
        except Exception as e:
            logger.warning("CanalFACe.enviar: %s", e)
            return {"ok": False, "estado": "pendiente", "mensaje": str(e)}

    @staticmethod
    def _parse(status: int, texto: str) -> dict:
        """Parseo del acuse FACe (por nombre local; robusto a prefijos). ⚠️[WSDL]."""
        out = {"ok": False, "estado": "pendiente", "numero_registro": None, "csv": None, "mensaje": None}
        if not texto:
            out["mensaje"] = f"HTTP {status} sin cuerpo"
            return out
        try:
            root = ET.fromstring(texto.encode("utf-8") if isinstance(texto, str) else texto)
        except Exception as e:
            out["mensaje"] = f"respuesta no parseable: {e}"
            return out
        fault = _buscar(root, "faultstring") or _buscar(root, "Fault")
        codigo = _buscar(root, "codigo")
        cod = codigo.text.strip() if (codigo is not None and codigo.text) else None
        nreg = _buscar(root, "numeroRegistro")
        out["numero_registro"] = nreg.text.strip() if (nreg is not None and nreg.text) else None
        # FACe: resultado.codigo == "0" → correcto.
        if status == 200 and cod == "0" and fault is None:
            out["ok"] = True
            out["estado"] = "enviado"
        else:
            desc = _buscar(root, "descripcion")
            out["mensaje"] = (desc.text if desc is not None and desc.text
                              else (fault.text if fault is not None and fault.text else f"codigo={cod}"))
        return out
