"""
Serialización XML de registros Verifactu (C3.3.2) — se ejecuta en el WORKER, no en
caja. Construye el `RegistroAlta`/`RegistroAnulacion` y el sobre del lote a remitir
a AEAT a partir de los datos legales ya guardados en el registro (payload + huella).

⚠️ MUY IMPORTANTE: los nombres de elementos, namespaces y el sobre SOAP DEBEN
contrastarse contra el XSD/WSDL oficial de AEAT (SuministroLR / RegFactuSistema
Facturacion) y el validador de preproducción antes de cualquier envío real. Todo el
formato se concentra aquí para que ese ajuste sea local y no toque ni el núcleo ni
el proveedor. El XML resultante se guarda como EVIDENCIA documental (C3.2).
"""

import json
import logging
from xml.sax.saxutils import escape

logger = logging.getLogger("fiscal.verifactu_xml")

# Datos del Sistema Informático de Facturación (SIF). ⚠️[completar con datos reales
# del productor y la versión declarada ante AEAT]
SIF = {
    "NombreRazon": "Smart Manager AI",
    "NIF": "",                      # NIF del productor del software ⚠️
    "NombreSistemaInformatico": "Smart Manager AI",
    "IdSistemaInformatico": "SM",
    "Version": "1.0",
    "NumeroInstalacion": "1",
}


def _meta(reg: dict) -> dict:
    try:
        return json.loads(reg.get("payload") or "{}")
    except Exception:
        return {}


def registro_xml(reg: dict, sif: dict | None = None) -> str:
    """XML de un registro (alta o anulación) a partir de la fila almacenada.
    ⚠️ estructura provisional, pendiente de cotejo con el XSD oficial."""
    from src.services.fiscal import verifactu_legal as legal
    sif = {**SIF, **(sif or {})}
    meta = _meta(reg)
    serie, numero = reg.get("serie"), reg.get("numero")
    es_anulacion = meta.get("kind") == "anulacion" or reg.get("tipo") == "anulacion"
    ns = legal.num_serie(serie, numero)

    def e(tag, val):
        return f"<{tag}>{escape(str(val if val is not None else ''))}</{tag}>"

    sif_xml = "".join(e(k, v) for k, v in sif.items())
    encadenamiento = (e("PrimerRegistro", "S") if not reg.get("hash_anterior")
                      else f"<RegistroAnterior>{e('Huella', reg.get('hash_anterior'))}</RegistroAnterior>")

    if es_anulacion:
        cuerpo = (
            e("IDEmisorFacturaAnulada", meta.get("nif_emisor")) +
            e("NumSerieFacturaAnulada", meta.get("num_serie_anulada") or ns) +
            e("FechaExpedicionFacturaAnulada", meta.get("fecha_expedicion")))
        raiz = "RegistroAnulacion"
    else:
        cuerpo = (
            e("IDEmisorFactura", meta.get("nif_emisor")) +
            e("NumSerieFactura", ns) +
            e("FechaExpedicionFactura", meta.get("fecha_expedicion")) +
            e("TipoFactura", meta.get("tipo_factura")) +
            e("CuotaTotal", meta.get("cuota_total")) +
            e("ImporteTotal", meta.get("importe_total")))
        raiz = "RegistroAlta"

    return (
        f'<{raiz}>'
        f'<IDVersion>1.0</IDVersion>'
        f'{cuerpo}'
        f'<SistemaInformatico>{sif_xml}</SistemaInformatico>'
        f'{encadenamiento}'
        f'<FechaHoraHusoGenRegistro>{escape(str(meta.get("fecha_gen") or ""))}</FechaHoraHusoGenRegistro>'
        f'<TipoHuella>01</TipoHuella>'           # 01 = SHA-256 ⚠️
        f'<Huella>{escape(str(reg.get("hash") or ""))}</Huella>'
        f'</{raiz}>')


def lote_xml(registros: list[dict], sif: dict | None = None) -> str:
    """Sobre del lote `RegFactuSistemaFacturacion` (varios registros). ⚠️[XSD/SOAP]."""
    cuerpo = "".join(registro_xml(r, sif) for r in registros)
    return (f'<RegFactuSistemaFacturacion>'
            f'<RegistroFactura>{cuerpo}</RegistroFactura>'
            f'</RegFactuSistemaFacturacion>')
