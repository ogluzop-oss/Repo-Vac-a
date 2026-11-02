"""
Emisor TicketBAI → LROE (C3.4-TBAI) — adaptador de ENVÍO a la Hacienda Foral
correspondiente (Araba/Bizkaia/Gipuzkoa). Mismo patrón que `EmisorVerifactu`:
transporte INYECTABLE (`callable(url, cuerpo:bytes, cfg)->(status:int, texto:str)`)
para validar el flujo completo en tests sin red ni certificado; en operación,
el transporte TLS real y el certificado se cablean igual que Verifactu —
reutilizando `emisores/tls.py` y la custodia `certificados.py` (SIN motor de
certificados paralelo).

A diferencia de Verifactu, TicketBAI exige la factura FIRMADA (XAdES-BES): el
`Firmante` (`FirmanteXAdES`, reutilizado de `firmantes/xades.py`) se inyecta
aquí y se aplica sobre el XML (`ticketbai_xml.registro_xml`) antes de enviar.
Sin certificado activo → sin firmante disponible → `disponible()=False` → el
worker deja el registro en espera (NUNCA se envía sin firmar).

Cada Diputación Foral opera su propio servicio LROE (Libro Registro de
Operaciones Económicas) con endpoint propio, pero las tres comparten el mismo
formato de factura TicketBAI — de ahí UNA sola clase con una tabla de
endpoints por territorio, en vez de tres clases duplicadas.

⚠️ IMPORTANTE: los endpoints son los PÚBLICOS conocidos de cada diputación;
CONTRASTAR contra el WSDL/manual de integración oficial de cada una antes de
producción — mismo criterio que ya advierte `verifactu_aeat.py` para AEAT.
"""

import logging
import xml.etree.ElementTree as ET

from src.services.fiscal.base import Emisor

logger = logging.getLogger("fiscal.emisor.ticketbai")

# Endpoints LROE por territorio y entorno. ⚠️[espejo/verificar WSDL o manual
# de integración oficial de cada Diputación Foral antes de producción]
_ENDPOINTS = {
    "araba": {
        "preproduccion": "https://ticketbai.araba.eus/tbai/test/recepcion",
        "produccion": "https://ticketbai.araba.eus/tbai/recepcion",
    },
    "bizkaia": {
        "preproduccion": "https://batuz.eus/lroePJ95/test/validarFactura",
        "produccion": "https://batuz.eus/lroePJ95/validarFactura",
    },
    "gipuzkoa": {
        "preproduccion": "https://tbai.egoitza.gipuzkoa.eus/WAS/HACI/TicketBaiHaciWEB/test/ticketBaiHaci",
        "produccion": "https://tbai.egoitza.gipuzkoa.eus/WAS/HACI/TicketBaiHaciWEB/ticketBaiHaci",
    },
}


class EmisorTicketBAI(Emisor):
    nombre = "ticketbai-lroe"

    def __init__(self, transporte=None, firmante=None, config=None):
        self._transporte = transporte
        self._firmante = firmante
        self.config = config or {}

    def disponible(self) -> bool:
        # TicketBAI exige factura FIRMADA → sin certificado activo (firmante)
        # no hay transmisión legal posible, igual que sin transporte mTLS.
        return (self._transporte is not None and self._firmante is not None
                and self._firmante.disponible())

    def endpoint(self, territorio: str, config: dict) -> str:
        ent = (config or {}).get("entorno", "preproduccion")
        tabla = _ENDPOINTS.get(territorio, _ENDPOINTS["araba"])
        return tabla.get(ent, tabla["preproduccion"])

    def _http(self, url, cuerpo, config):
        """Transporte real de respaldo (requests, sin mTLS). El transporte mTLS
        inyectado (producción) lo construye `factory._transporte_mtls`."""
        import requests
        r = requests.post(url, data=cuerpo,
                          headers={"Content-Type": "application/xml; charset=utf-8"},
                          timeout=int((config or {}).get("timeout", 30)))
        return r.status_code, r.text

    def enviar(self, registro, config: dict) -> dict:
        from src.db import fiscal as fdb
        from src.services.fiscal import ticketbai_xml as tx
        try:
            fila = fdb.obtener_registro(registro.id) if getattr(registro, "id", None) else None
            if not fila:
                return {"ok": False, "estado": "pendiente", "mensaje": "registro no encontrado"}
            if not self.disponible():
                return {"ok": False, "estado": "pendiente",
                       "mensaje": "sin certificado activo (TicketBAI exige factura firmada)"}
            territorio = (config or {}).get("territorio") or "araba"
            xml_sin_firmar = tx.registro_xml(fila)
            xml_firmado = self._firmante.firmar_xml(xml_sin_firmar)
            if not xml_firmado:
                return {"ok": False, "estado": "pendiente", "mensaje": "no se pudo firmar (XAdES)"}
            transporte = self._transporte or self._http
            status, texto = transporte(self.endpoint(territorio, config), xml_firmado, config)
            res = self._parse(status, texto)
            self._evidencias(fila, xml_firmado, texto)
            return res
        except Exception as e:
            logger.warning("EmisorTicketBAI.enviar(reg=%s): %s", getattr(registro, "id", "?"), e)
            return {"ok": False, "estado": "pendiente", "mensaje": str(e)}

    def _evidencias(self, fila, xml_firmado: bytes, respuesta: str):
        try:
            from src.services.fiscal.evidencias import guardar_evidencia
            guardar_evidencia(fila, "xml", xml_firmado, id_empresa=fila.get("id_empresa"))
            if respuesta:
                guardar_evidencia(fila, "acuse", respuesta, id_empresa=fila.get("id_empresa"))
        except Exception as e:
            logger.debug("No se pudieron guardar evidencias TicketBAI: %s", e)

    @staticmethod
    def _local(elem) -> str:
        t = elem.tag
        return t.rsplit("}", 1)[-1] if "}" in t else t

    @classmethod
    def _buscar(cls, root, nombre):
        for el in root.iter():
            if cls._local(el) == nombre:
                return el
        return None

    @classmethod
    def _parse(cls, status: int, texto: str) -> dict:
        """Parseo best-effort del acuse LROE. ⚠️[nombres de elementos a
        confirmar contra la respuesta real de cada diputación; se buscan por
        nombre local para ser robusto ante namespaces/prefijos distintos entre
        Araba/Bizkaia/Gipuzkoa — mismo criterio que `EmisorVerifactu._parse`]."""
        out = {"ok": False, "estado": "pendiente", "mensaje": None}
        if not texto:
            out["mensaje"] = f"HTTP {status} sin cuerpo"
            return out
        try:
            root = ET.fromstring(texto.encode("utf-8") if isinstance(texto, str) else texto)
        except Exception as e:
            out["mensaje"] = f"respuesta no parseable: {e}"
            return out
        for nombre_error in ("DescripcionError", "Fault", "faultstring"):
            el = cls._buscar(root, nombre_error)
            if el is not None and (el.text or "").strip():
                out["mensaje"] = el.text.strip()
                out["estado"] = "rechazado"
                return out
        estado = None
        for nombre_estado in ("EstadoRegistro", "Estado", "EstadoEnvio"):
            el = cls._buscar(root, nombre_estado)
            if el is not None and el.text:
                estado = el.text.strip()
                break
        out["estado_lroe"] = estado
        if status == 200 and estado and estado.lower() in ("correcto", "aceptado", "ok"):
            out["ok"] = True
            out["estado"] = "enviado"
        elif estado:
            out["estado"] = "pendiente"
            out["mensaje"] = f"estado LROE: {estado}"
        return out
