"""
Serialización XML de registros Verifactu (C3.3.1.1) — CONFORME al XSD oficial.

Construye `RegFactuSistemaFacturacion` (Cabecera + RegistroFactura → RegistroAlta /
RegistroAnulacion) con los namespaces oficiales de AEAT. Se ejecuta en el WORKER
(no en caja) a partir de los datos legales del registro (payload + huella).

Usa **stdlib** (`xml.etree`) para no añadir dependencia binaria en runtime; la
CONFORMIDAD se valida contra los XSD (`esquemas/`) en tests/build con `lxml`.
El XML se valida contra el esquema oficial (espejo, ver `esquemas/PROCEDENCIA.md`).
"""

import json
import logging
import xml.etree.ElementTree as ET

from src.services.fiscal.esquemas import NS

logger = logging.getLogger("fiscal.verifactu_xml")

_SF = "{%s}" % NS["sf"]
_LR = "{%s}" % NS["sfLR"]

# Datos del Sistema Informático de Facturación (SIF). ⚠️[completar NIF del productor
# y la versión/instalación declarados ante AEAT antes de producción]
SIF = {
    "NombreRazon": "Smart Manager AI",
    "NIF": "B00000000",
    "NombreSistemaInformatico": "Smart Manager AI",
    "IdSistemaInformatico": "SM",
    "Version": "1.0",
    "NumeroInstalacion": "1",
    "TipoUsoPosibleSoloVerifactu": "S",
    "TipoUsoPosibleMultiOT": "N",
    "IndicadorMultiplesOT": "N",
}


def _e(parent, tag, text=None, ns=_SF):
    el = ET.SubElement(parent, ns + tag)
    if text is not None:
        el.text = str(text)
    return el


def _meta(reg: dict) -> dict:
    try:
        return json.loads(reg.get("payload") or "{}")
    except Exception:
        return {}


def _sif(parent, sif: dict):
    s = _e(parent, "SistemaInformatico")
    _e(s, "NombreRazon", sif["NombreRazon"])
    _e(s, "NIF", sif["NIF"])
    _e(s, "NombreSistemaInformatico", sif["NombreSistemaInformatico"])
    _e(s, "IdSistemaInformatico", sif["IdSistemaInformatico"])
    _e(s, "Version", sif["Version"])
    _e(s, "NumeroInstalacion", sif["NumeroInstalacion"])
    _e(s, "TipoUsoPosibleSoloVerifactu", sif["TipoUsoPosibleSoloVerifactu"])
    _e(s, "TipoUsoPosibleMultiOT", sif["TipoUsoPosibleMultiOT"])
    _e(s, "IndicadorMultiplesOT", sif["IndicadorMultiplesOT"])


def _encadenamiento(parent, reg: dict):
    enc = _e(parent, "Encadenamiento")
    if not reg.get("hash_anterior"):
        _e(enc, "PrimerRegistro", "S")
        return
    ra = _e(enc, "RegistroAnterior")
    ant = _registro_anterior(reg)
    _e(ra, "IDEmisorFactura", ant.get("nif", ""))
    _e(ra, "NumSerieFactura", ant.get("numserie", ""))
    _e(ra, "FechaExpedicionFactura", ant.get("fecha", ""))
    _e(ra, "Huella", reg.get("hash_anterior"))


def _registro_anterior(reg: dict) -> dict:
    """Datos IDFactura del registro anterior (misma empresa/serie, numero-1)."""
    from src.services.fiscal import verifactu_legal as legal
    try:
        from src.db import fiscal as F
        prev = F.obtener_por_serie_numero(reg.get("id_empresa"), reg.get("serie"),
                                          int(reg.get("numero") or 1) - 1)
        if prev:
            m = _meta(prev)
            return {"nif": m.get("nif_emisor", ""),
                    "numserie": legal.num_serie(prev.get("serie"), prev.get("numero")),
                    "fecha": m.get("fecha_expedicion", "")}
    except Exception as e:
        logger.debug("registro anterior no resuelto: %s", e)
    return {}


def _registro_alta(parent, reg: dict, meta: dict):
    from src.services.fiscal import verifactu_legal as legal
    a = _e(parent, "RegistroAlta")
    _e(a, "IDVersion", "1.0")
    idf = _e(a, "IDFactura")
    _e(idf, "IDEmisorFactura", meta.get("nif_emisor", ""))
    _e(idf, "NumSerieFactura", legal.num_serie(reg.get("serie"), reg.get("numero")))
    _e(idf, "FechaExpedicionFactura", meta.get("fecha_expedicion", ""))
    _e(a, "NombreRazonEmisor", meta.get("nombre_emisor", ""))
    _e(a, "TipoFactura", meta.get("tipo_factura", "F2"))
    _e(a, "DescripcionOperacion", meta.get("descripcion", "Venta"))
    desg = _e(a, "Desglose")
    for d in meta.get("desglose") or []:
        det = _e(desg, "DetalleDesglose")
        if d.get("clave_regimen"):
            _e(det, "ClaveRegimen", d["clave_regimen"])
        _e(det, "CalificacionOperacion", d.get("calificacion", "S1"))
        if d.get("tipo") is not None:
            _e(det, "TipoImpositivo", d["tipo"])
        _e(det, "BaseImponibleOimporteNoSujeto", d.get("base", "0.00"))
        if d.get("cuota") is not None:
            _e(det, "CuotaRepercutida", d["cuota"])
    _e(a, "CuotaTotal", meta.get("cuota_total", "0.00"))
    _e(a, "ImporteTotal", meta.get("importe_total", "0.00"))
    _encadenamiento(a, reg)
    _sif(a, {**SIF, **(meta.get("sif") or {})})
    _e(a, "FechaHoraHusoGenRegistro", meta.get("fecha_gen", ""))
    _e(a, "TipoHuella", "01")
    _e(a, "Huella", reg.get("hash", ""))


def _registro_anulacion(parent, reg: dict, meta: dict):
    from src.services.fiscal import verifactu_legal as legal
    a = _e(parent, "RegistroAnulacion")
    _e(a, "IDVersion", "1.0")
    idf = _e(a, "IDFactura")
    _e(idf, "IDEmisorFacturaAnulada", meta.get("nif_emisor", ""))
    _e(idf, "NumSerieFacturaAnulada",
       meta.get("num_serie_anulada") or legal.num_serie(reg.get("serie"), reg.get("numero")))
    _e(idf, "FechaExpedicionFacturaAnulada", meta.get("fecha_expedicion", ""))
    _encadenamiento(a, reg)
    _sif(a, {**SIF, **(meta.get("sif") or {})})
    _e(a, "FechaHoraHusoGenRegistro", meta.get("fecha_gen", ""))
    _e(a, "TipoHuella", "01")
    _e(a, "Huella", reg.get("hash", ""))


def _registro(parent, reg: dict):
    meta = _meta(reg)
    if meta.get("kind") == "anulacion" or reg.get("tipo") == "anulacion":
        _registro_anulacion(parent, reg, meta)
    else:
        _registro_alta(parent, reg, meta)


def cabecera(parent, obligado: dict):
    cab = _e(parent, "Cabecera", ns=_LR)
    obl = _e(cab, "ObligadoEmision")
    _e(obl, "NombreRazon", obligado.get("nombre", ""))
    _e(obl, "NIF", obligado.get("nif", ""))


def lote_xml(registros: list[dict], obligado: dict | None = None) -> bytes:
    """Sobre `RegFactuSistemaFacturacion` (Cabecera + hasta 1000 RegistroFactura).
    Devuelve bytes UTF-8 listos para el cuerpo SOAP. Conforme a SuministroLR.xsd."""
    if obligado is None:
        m0 = _meta(registros[0]) if registros else {}
        obligado = {"nombre": m0.get("nombre_emisor", ""), "nif": m0.get("nif_emisor", "")}
    root = ET.Element(_LR + "RegFactuSistemaFacturacion")
    cabecera(root, obligado)
    for reg in registros[:1000]:
        rf = _e(root, "RegistroFactura", ns=_LR)
        _registro(rf, reg)
    return ET.tostring(root, encoding="utf-8")


def registro_xml(reg: dict) -> bytes:
    """XML de un único registro envuelto (para evidencia/validación individual)."""
    return lote_xml([reg])


def validar(xml_bytes) -> tuple:
    """(ok, errores) validando contra el XSD oficial (espejo). Requiere lxml."""
    from src.services.fiscal.esquemas import validar as _validar
    return _validar(xml_bytes, "SuministroLR.xsd")
