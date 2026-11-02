"""
Formato LEGAL de TicketBAI (C3.4-TBAI) — identificador visible, huella de
encadenado y QR de cotejo del régimen foral del País Vasco (Araba/Bizkaia/
Gipuzkoa). Funciones PURAS y testables, mismo patrón que `verifactu_legal.py`:
aquí se aísla TODO el formato legal para que el ajuste fino contra el XSD/LROE
oficial de cada Diputación Foral sea trivial y no afecte al núcleo ni a Verifactu.

⚠️ IMPORTANTE: TicketBAI exige una factura FIRMADA (XAdES-BES) por el software;
el encadenamiento LEGAL real que viaja en el XML referencia el VALOR DE FIRMA
de la factura anterior (`SignatureValueFirmaFacturaAnterior`), no un hash
independiente. Aquí se definen DOS cosas distintas, a propósito:
  1) `huella_alta`/`huella_anulacion`: la HUELLA INTERNA (SHA-256, mismo
     mecanismo de encadenado neutro que ya usa `fiscal_registros`/Verifactu)
     que alimenta `campos_hash`/`huella_fn` de `src.db.fiscal.insertar_registro`
     — es la que valida `cadena_valida()` para auditoría del núcleo.
  2) `identificador_tbai`/`contenido_qr`: el identificador VISIBLE TicketBAI y
     el QR de cotejo, que es lo que de verdad valida la Hacienda Foral.
El XML firmado (`ticketbai_xml.py`) usa la huella interna como referencia de
encadenado dentro del documento; `EmisorTicketBAI` es quien añade la firma
XAdES real antes del envío. Antes de producción: contrastar nombres/orden
exactos de campos, el algoritmo oficial del CRC del identificador y las URLs
de cotejo contra el XSD y el manual de integración de cada Diputación Foral.
"""

import binascii
import hashlib
from urllib.parse import urlencode

TERRITORIOS = ("araba", "bizkaia", "gipuzkoa")

# Orden de los campos que entran en la HUELLA INTERNA de auditoría del núcleo
# (encadenado neutro, igual mecanismo que Verifactu) aplicado a los campos
# legales propios de TicketBAI.
ORDEN_ALTA = ("NIFEmisor", "SerieFactura", "NumFactura", "FechaExpedicionFactura",
             "HoraExpedicionFactura", "ImporteTotalFactura", "Huella")
ORDEN_ANULACION = ("NIFEmisor", "SerieFacturaAnulada", "NumFacturaAnulada",
                   "FechaExpedicionFacturaAnulada", "Huella")

# QR de cotejo oficial — mismo esquema de parámetros TicketBAI, solo cambia el
# host por Diputación Foral. ⚠️[verificar contra el PDF/manual QR oficial de
# cada diputación antes de producción].
_URL_QR = {
    "araba":    "https://ticketbai.araba.eus/tbai/qrtbai/",
    "bizkaia":  "https://batuz.eus/QRTBAI/",
    "gipuzkoa": "https://tbai.egoitza.gipuzkoa.eus/qr/",
}

LEYENDA = "TicketBAI"
LEYENDA_LARGA = "Factura verificable en la sede electrónica de la Hacienda Foral"
MARCADOR_SIN_CERTIFICADO = "SIN-CERTIFICADO"   # nunca se presenta como identificador válido


def num_factura(serie, numero) -> str:
    """Identificador NumFactura (serie + número) a efectos de referencia interna."""
    return f"{serie}/{numero}"


def _serializa(campos: dict, hash_anterior, orden) -> str:
    d = dict(campos)
    d["Huella"] = hash_anterior or ""
    cadena = "&".join(f"{k}={d.get(k, '')}" for k in orden)
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest().upper()


def huella_alta(campos: dict, hash_anterior) -> str:
    """Huella interna (núcleo) de un registro de ALTA, encadenada con la anterior."""
    return _serializa(campos, hash_anterior, ORDEN_ALTA)


def huella_anulacion(campos: dict, hash_anterior) -> str:
    """Huella interna (núcleo) de un registro de ANULACION, encadenada con la anterior."""
    return _serializa(campos, hash_anterior, ORDEN_ANULACION)


def campos_alta(serie, numero, meta: dict) -> dict:
    """Campos de la huella interna de ALTA (sin Huella, que la inyecta el serializador)."""
    return {
        "NIFEmisor": meta.get("nif_emisor", ""),
        "SerieFactura": serie,
        "NumFactura": str(numero),
        "FechaExpedicionFactura": meta.get("fecha_expedicion", ""),
        "HoraExpedicionFactura": meta.get("hora_expedicion", ""),
        "ImporteTotalFactura": meta.get("importe_total", ""),
    }


def campos_anulacion(serie, numero, meta: dict) -> dict:
    return {
        "NIFEmisor": meta.get("nif_emisor", ""),
        "SerieFacturaAnulada": meta.get("serie_anulada") or serie,
        "NumFacturaAnulada": meta.get("num_anulada") or str(numero),
        "FechaExpedicionFacturaAnulada": meta.get("fecha_expedicion", ""),
    }


def _crc(texto: str) -> str:
    """CRC corto (4 dígitos) del identificador visible. ⚠️[confirmar el
    algoritmo OFICIAL exacto contra el manual TicketBAI antes de producción;
    aquí se usa un CRC-32 truncado determinista — ESTABLE y reproducible,
    nunca un valor aleatorio o inventado]."""
    return f"{(binascii.crc32(texto.encode('utf-8')) & 0xFFFF):04d}"[-4:]


def identificador_tbai(nif_emisor, fecha_expedicion_ddmmyy, num_serie_cert_hex) -> str:
    """Identificador TBAI VISIBLE: TBAI-<NIF>-<ddmmyy>-<8 car. serie certificado>-<CRC>.
    Requiere el Nº de serie (hex) del certificado ACTIVO que firma la factura — sin
    certificado no existe identificador legal real (ver `MARCADOR_SIN_CERTIFICADO`,
    usado por el llamador en `ticketbai.py` en vez de construir uno falso aquí)."""
    serie_hex = (num_serie_cert_hex or "").upper()[-8:].rjust(8, "0")
    base = f"TBAI-{nif_emisor}-{fecha_expedicion_ddmmyy}-{serie_hex}"
    return f"{base}-{_crc(base)}"


def contenido_qr(territorio, identificador, serie, numero, importe_total) -> str:
    """URL de cotejo del QR TicketBAI de la Diputación Foral del territorio dado."""
    base = _URL_QR.get(territorio, _URL_QR["araba"])
    params = urlencode({"id": identificador, "s": serie, "nf": numero, "i": importe_total})
    return f"{base}?{params}"
