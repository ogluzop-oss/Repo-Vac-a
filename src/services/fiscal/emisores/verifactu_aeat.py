"""
Emisor Verifactu → AEAT (C3.3.1.1) — adaptador de ENVÍO conforme al WSDL oficial.

Encapsula toda la especificidad de AEAT (sobre SOAP document/literal, POST, parseo
real de la respuesta) para no tocar el worker congelado: el worker solo orquesta.
Construye el cuerpo con `verifactu_xml.lote_xml` (XML validado contra XSD), envía y
persiste la trazabilidad (estado/CSV) + las EVIDENCIAS (XML y acuse).

Transporte INYECTABLE (`callable(url, cuerpo:bytes, cfg)->(status:int, texto:str)`)
para validar el flujo completo en tests sin red ni certificado. En operación, el
transporte TLS con certificado y el paso a PRODUCCIÓN se consolidan en C3.5; sin
transporte/certificado, `disponible()=False` y el worker deja el registro en espera.

TiempoEsperaEnvio (throttling de AEAT) se respeta mediante una ventana de pacing en
memoria (a nivel de proceso) SIN tocar el worker. ⚠️ El honrado exacto por entrada
de cola persistente requeriría un hook aditivo al worker (pendiente de decisión).
"""

import datetime as _dt
import logging
import xml.etree.ElementTree as ET

from src.services.fiscal.base import Emisor

logger = logging.getLogger("fiscal.emisor.verifactu")

# Endpoints del web service Verifactu (operación RegFactuSistemaFacturacion,
# document/literal, soapAction=""). Confirmados contra el WSDL oficial (espejo).
_ENDPOINT = {
    "preproduccion": "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
    "produccion": "https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
}
_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"

# Ventana de pacing por empresa (proceso) para respetar TiempoEsperaEnvio.
_proximo_envio: dict = {}


def _local(elem) -> str:
    t = elem.tag
    return t.rsplit("}", 1)[-1] if "}" in t else t


def _buscar(root, nombre):
    for el in root.iter():
        if _local(el) == nombre:
            return el
    return None


def _buscar_todos(root, nombre):
    return [el for el in root.iter() if _local(el) == nombre]


class EmisorVerifactu(Emisor):
    nombre = "verifactu-aeat"

    def __init__(self, transporte=None, config=None):
        self._transporte = transporte
        self.config = config or {}

    def disponible(self) -> bool:
        return self._transporte is not None or bool(self.config.get("cert_listo"))

    def endpoint(self, config: dict) -> str:
        ent = (config or {}).get("entorno", "preproduccion")
        return _ENDPOINT.get(ent, _ENDPOINT["preproduccion"])

    def _sobre_soap(self, cuerpo_xml: bytes) -> bytes:
        body = cuerpo_xml.decode("utf-8") if isinstance(cuerpo_xml, bytes) else cuerpo_xml
        env = (f'<soapenv:Envelope xmlns:soapenv="{_SOAP_NS}">'
               f'<soapenv:Body>{body}</soapenv:Body></soapenv:Envelope>')
        return env.encode("utf-8")

    def _http(self, url: str, cuerpo: bytes, config: dict):
        """Transporte real (requests + certificado). El certificado se cablea en C3.5."""
        import requests
        cert = config.get("cert")           # (ruta_pem, ruta_key) — C3.5
        r = requests.post(url, data=cuerpo,
                          headers={"Content-Type": "text/xml; charset=utf-8",
                                   "SOAPAction": ""},
                          cert=cert, timeout=30)
        return r.status_code, r.text

    def enviar(self, registro, config: dict) -> dict:
        from src.db import fiscal as fdb
        from src.services.fiscal import verifactu_xml as vx
        try:
            fila = fdb.obtener_registro(registro.id) if getattr(registro, "id", None) else None
            if not fila:
                return {"ok": False, "estado": "pendiente", "mensaje": "registro no encontrado"}
            emp = fila.get("id_empresa")
            # Respeta el throttling de AEAT (pacing en memoria).
            espera_hasta = _proximo_envio.get(emp)
            if espera_hasta and _dt.datetime.now() < espera_hasta:
                return {"ok": False, "estado": "pendiente", "mensaje": "espera AEAT (TiempoEsperaEnvio)"}

            cuerpo = self._sobre_soap(vx.lote_xml([fila]))
            transporte = self._transporte or self._http
            status, texto = transporte(self.endpoint(config), cuerpo, config)
            res = self._parse(status, texto)

            if res.get("espera"):
                _proximo_envio[emp] = _dt.datetime.now() + _dt.timedelta(seconds=int(res["espera"]))
            fdb.actualizar_aeat(registro.id, estado_aeat=res.get("estado_aeat"),
                                csv_aeat=res.get("csv"))
            self._evidencias(fila, cuerpo, texto)
            return res
        except Exception as e:
            logger.warning("EmisorVerifactu.enviar(reg=%s): %s", getattr(registro, "id", "?"), e)
            return {"ok": False, "estado": "pendiente", "mensaje": str(e)}

    def _evidencias(self, fila, sobre: bytes, respuesta: str):
        try:
            from src.services.fiscal.evidencias import guardar_evidencia
            guardar_evidencia(fila, "xml", sobre.decode("utf-8"), id_empresa=fila.get("id_empresa"))
            if respuesta:
                guardar_evidencia(fila, "acuse", respuesta, id_empresa=fila.get("id_empresa"))
        except Exception as e:
            logger.debug("No se pudieron guardar evidencias AEAT: %s", e)

    @staticmethod
    def _parse(status: int, texto: str) -> dict:
        """Parseo real del acuse AEAT (RespuestaSuministro.xsd). Busca por nombre
        local (robusto ante prefijos/namespaces del espejo vs oficial)."""
        out = {"ok": False, "estado": "pendiente", "estado_aeat": None, "csv": None,
               "mensaje": None, "espera": None}
        if not texto:
            out["mensaje"] = f"HTTP {status} sin cuerpo"
            return out
        try:
            root = ET.fromstring(texto.encode("utf-8") if isinstance(texto, str) else texto)
        except Exception as e:
            out["mensaje"] = f"respuesta no parseable: {e}"
            return out

        # SOAP Fault → rechazo.
        fault = _buscar(root, "Fault")
        if fault is not None:
            fs = _buscar(fault, "faultstring")
            out["mensaje"] = (fs.text if fs is not None else "SOAP Fault")
            out["estado_aeat"] = "Incorrecto"
            return out

        estado_envio = _txt(_buscar(root, "EstadoEnvio"))
        out["csv"] = _txt(_buscar(root, "CSV"))
        out["espera"] = _num(_txt(_buscar(root, "TiempoEsperaEnvio")))
        lineas = _buscar_todos(root, "RespuestaLinea")
        estado_linea, cod_err, desc_err, duplicado = None, None, None, False
        if lineas:
            l0 = lineas[0]
            estado_linea = _txt(_buscar(l0, "EstadoRegistro"))
            cod_err = _txt(_buscar(l0, "CodigoErrorRegistro"))
            desc_err = _txt(_buscar(l0, "DescripcionErrorRegistro"))
            duplicado = _buscar(l0, "RegistroDuplicado") is not None

        out["estado_aeat"] = estado_linea or estado_envio
        out["mensaje"] = desc_err or (f"error {cod_err}" if cod_err else None)
        estado_eval = (estado_linea or estado_envio or "").lower()
        if status == 200 and (estado_eval in ("correcto", "aceptadoconerrores") or duplicado):
            out["ok"] = True
            out["estado"] = "enviado"
        # ParcialmenteCorrecto/Incorrecto con esta línea rechazada → reintento (ok=False).
        return out


def _txt(el):
    return el.text.strip() if (el is not None and el.text) else None


def _num(v):
    try:
        return int(float(v)) if v is not None else None
    except Exception:
        return None
