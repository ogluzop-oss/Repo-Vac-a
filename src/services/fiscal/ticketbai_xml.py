"""
Serialización XML de factura TicketBAI (C3.4-TBAI) — SIN FIRMAR. La firma
XAdES-BES real la añade `FirmanteXAdES` (reutilizado de `firmantes/xades.py`)
sobre el XML que construye este módulo, antes del envío a la LROE de la
Diputación Foral correspondiente (`emisores/ticketbai_lroe.py`).

Estructura informada por la especificación pública TicketBAI (elemento raíz
`T:TicketBai`), compartida por Araba/Bizkaia/Gipuzkoa (solo cambian los
endpoints de envío y el host del QR, no el formato de factura). Usa **stdlib**
(`xml.etree`), igual que `verifactu_xml.py`, para no añadir una dependencia
binaria en runtime.

⚠️ IMPORTANTE: contrastar nombres/orden EXACTOS de los elementos (y las
particularidades menores de cada diputación) contra el XSD oficial TicketBAI
antes de producción — mismo criterio que ya se advierte en `verifactu_xml.py`
para el XSD de AEAT.
"""

import json
import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger("fiscal.ticketbai_xml")

_NS = "urn:ticketbai:emision"
_T = "{%s}" % _NS

# Datos del software (declarados ante la Diputación al obtener la licencia
# TBAI). ⚠️[completar LicenciaTBAI real por territorio antes de producción].
SOFTWARE = {
    "LicenciaTBAI": "",
    "EntidadDesarrolladoraNIF": "B00000000",
    "Nombre": "Smart Manager AI",
    "Version": "1.0",
}


def _e(parent, tag, text=None):
    el = ET.SubElement(parent, _T + tag)
    if text is not None:
        el.text = str(text)
    return el


def _meta(reg: dict) -> dict:
    try:
        return json.loads(reg.get("payload") or "{}")
    except Exception:
        return {}


def _encadenamiento(parent, reg: dict):
    """`EncadenamientoFacturaAnterior` — referencia a la factura anterior de la
    misma serie. Se omite en la primera factura de la serie (sin anterior)."""
    if not reg.get("hash_anterior"):
        return
    enc = _e(parent, "EncadenamientoFacturaAnterior")
    prev, pmeta = None, {}
    try:
        from src.db import fiscal as F
        prev = F.obtener_por_serie_numero(reg.get("id_empresa"), reg.get("serie"),
                                          int(reg.get("numero") or 1) - 1)
        pmeta = _meta(prev) if prev else {}
    except Exception as e:
        logger.debug("factura anterior no resuelta: %s", e)
    _e(enc, "SerieFacturaAnterior", (prev or {}).get("serie") or reg.get("serie"))
    _e(enc, "NumFacturaAnterior", (prev or {}).get("numero") or "")
    _e(enc, "FechaExpedicionFacturaAnterior", pmeta.get("fecha_expedicion", ""))
    # ⚠️ El valor legal real es el SignatureValue (XAdES) de la factura anterior.
    # Aquí se referencia la huella interna encadenada (ver ticketbai_legal.py);
    # ajustar a la firma real si la verificación contra el XSD lo exige.
    _e(enc, "SignatureValueFirmaFacturaAnterior", (reg.get("hash_anterior") or "")[:100])


def _desglose_iva(parent, meta: dict):
    td = _e(parent, "TipoDesglose")
    df = _e(td, "DesgloseFactura")
    suj = _e(df, "Sujeta")
    noex = _e(suj, "NoExenta")
    for d in (meta.get("desglose") or [{}]):
        det = _e(noex, "DetalleNoExenta")
        _e(det, "TipoNoExenta", "S1")
        div = _e(det, "DesgloseIVA")
        di = _e(div, "DetalleIVA")
        _e(di, "BaseImponible", d.get("base", "0.00"))
        if d.get("tipo") is not None:
            _e(di, "TipoImpositivo", d["tipo"])
        _e(di, "CuotaImpuesto", d.get("cuota", "0.00"))


def _factura_alta(parent, reg: dict, meta: dict):
    fac = _e(parent, "Factura")
    cab = _e(fac, "CabeceraFactura")
    _e(cab, "SerieFactura", reg.get("serie"))
    _e(cab, "NumFactura", reg.get("numero"))
    _e(cab, "FechaExpedicionFactura", meta.get("fecha_expedicion", ""))
    _e(cab, "HoraExpedicionFactura", meta.get("hora_expedicion", ""))
    datos = _e(fac, "DatosFactura")
    _e(datos, "DescripcionFactura", meta.get("descripcion", "Venta"))
    _e(datos, "ImporteTotalFactura", meta.get("importe_total", "0.00"))
    _desglose_iva(fac, meta)


def _factura_anulacion(parent, reg: dict, meta: dict):
    fac = _e(parent, "Factura")
    cab = _e(fac, "CabeceraAnulacion")
    _e(cab, "SerieFacturaAnulada", meta.get("serie_anulada") or reg.get("serie"))
    _e(cab, "NumFacturaAnulada", meta.get("num_anulada") or reg.get("numero"))
    _e(cab, "FechaExpedicionFacturaAnulada", meta.get("fecha_expedicion", ""))


def _sujetos(parent, meta: dict):
    suj = _e(parent, "Sujetos")
    emi = _e(suj, "Emisor")
    _e(emi, "NIF", meta.get("nif_emisor", ""))
    _e(emi, "ApellidosNombreRazonSocial", meta.get("nombre_emisor", ""))


def _software(parent):
    sw = _e(parent, "Software")
    _e(sw, "LicenciaTBAI", SOFTWARE["LicenciaTBAI"])
    ed = _e(sw, "EntidadDesarrolladora")
    _e(ed, "NIF", SOFTWARE["EntidadDesarrolladoraNIF"])
    _e(sw, "Nombre", SOFTWARE["Nombre"])
    _e(sw, "Version", SOFTWARE["Version"])


def registro_xml(reg: dict) -> bytes:
    """XML TicketBai SIN FIRMAR de un registro (alta o anulación). `reg` es la
    fila de `fiscal_registros` (dict), con `payload` = meta legal (JSON)."""
    meta = _meta(reg)
    es_anulacion = meta.get("kind") == "anulacion" or reg.get("tipo") == "anulacion"
    root = ET.Element(_T + "TicketBai")
    cab = _e(root, "Cabecera")
    _e(cab, "IDVersionTBAI", "1.2")
    _sujetos(root, meta)
    if es_anulacion:
        _factura_anulacion(root, reg, meta)
    else:
        _factura_alta(root, reg, meta)
    huella = _e(root, "HuellaTBAI")
    _encadenamiento(huella, reg)
    _e(huella, "Huella", reg.get("hash", ""))
    _software(root)
    return ET.tostring(root, encoding="utf-8")
