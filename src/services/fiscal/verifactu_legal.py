"""
Formato LEGAL de Verifactu (C3.3) — huella encadenada, nº de serie y QR de cotejo.

Funciones PURAS y testables que materializan el formato de la Orden HAC/1177/2024
(especificaciones técnicas de Verifactu) sobre el núcleo neutro ya congelado:

- `huella_alta` / `huella_anulacion`: SHA-256 sobre la concatenación `clave=valor&…`
  en el ORDEN legal, en hexadecimal MAYÚSCULAS, encadenando la huella anterior.
- `contenido_qr`: URL del servicio de cotejo de AEAT + parámetros de la factura.
- `num_serie`, leyendas obligatorias.

⚠️ IMPORTANTE: los nombres/orden de campos, el formato de fechas y la URL de cotejo
deben CONTRASTARSE contra el XSD/validador oficial de AEAT antes de producción
(ver C3.3.2/C3.3.3). Aquí se aísla todo el formato legal en un único punto para que
ese ajuste sea trivial y NO afecte al núcleo.
"""

import hashlib
from urllib.parse import urlencode

# Orden legal de los campos de la huella (Orden HAC/1177/2024). ⚠️[verificar XSD]
ORDEN_ALTA = ("IDEmisorFactura", "NumSerieFactura", "FechaExpedicionFactura",
              "TipoFactura", "CuotaTotal", "ImporteTotal", "Huella",
              "FechaHoraHusoGenRegistro")
ORDEN_ANULACION = ("IDEmisorFacturaAnulada", "NumSerieFacturaAnulada",
                   "FechaExpedicionFacturaAnulada", "Huella",
                   "FechaHoraHusoGenRegistro")

# Servicio de cotejo del QR (preproducción vs producción). ⚠️[verificar URL/params]
_URL_QR = {
    "preproduccion": "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR",
    "produccion": "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR",
}

LEYENDA = "VERI*FACTU"
LEYENDA_LARGA = "Factura verificable en la sede electrónica de la AEAT"


def num_serie(serie, numero) -> str:
    """Identificador NumSerieFactura a partir de la serie efectiva y el nº correlativo."""
    return f"{serie}/{numero}"


def _serializa(campos: dict, hash_anterior, orden) -> str:
    d = dict(campos)
    d["Huella"] = hash_anterior or ""
    cadena = "&".join(f"{k}={d.get(k, '')}" for k in orden)
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest().upper()


def huella_alta(campos: dict, hash_anterior) -> str:
    """Huella legal de un registro de ALTA, encadenada con la anterior."""
    return _serializa(campos, hash_anterior, ORDEN_ALTA)


def huella_anulacion(campos: dict, hash_anterior) -> str:
    """Huella legal de un registro de ANULACION, encadenada con la anterior."""
    return _serializa(campos, hash_anterior, ORDEN_ANULACION)


def campos_alta(serie, numero, meta: dict) -> dict:
    """Campos de la huella de ALTA (sin Huella, que la inyecta el serializador).
    `meta` aporta los datos no derivables (NIF, fechas, importes, tipo)."""
    return {
        "IDEmisorFactura": meta.get("nif_emisor", ""),
        "NumSerieFactura": num_serie(serie, numero),
        "FechaExpedicionFactura": meta.get("fecha_expedicion", ""),
        "TipoFactura": meta.get("tipo_factura", ""),
        "CuotaTotal": meta.get("cuota_total", ""),
        "ImporteTotal": meta.get("importe_total", ""),
        "FechaHoraHusoGenRegistro": meta.get("fecha_gen", ""),
    }


def campos_anulacion(serie, numero, meta: dict) -> dict:
    return {
        "IDEmisorFacturaAnulada": meta.get("nif_emisor", ""),
        "NumSerieFacturaAnulada": meta.get("num_serie_anulada") or num_serie(serie, numero),
        "FechaExpedicionFacturaAnulada": meta.get("fecha_expedicion", ""),
        "FechaHoraHusoGenRegistro": meta.get("fecha_gen", ""),
    }


def contenido_qr(nif, num_serie_factura, fecha_expedicion, importe_total,
                 entorno="preproduccion") -> str:
    """URL de cotejo del QR Verifactu. ⚠️[verificar nombres de parámetros]."""
    base = _URL_QR.get(entorno, _URL_QR["preproduccion"])
    params = urlencode({"nif": nif, "numserie": num_serie_factura,
                        "fecha": fecha_expedicion, "importe": importe_total})
    return f"{base}?{params}"
