"""
FASE 4.9/4.10 — EDI empresarial + PEPPOL (estructura preparada, sin certificar/producción).

- EDI (4.9): registro de intercambio documental B2B (EDIFACT/UBL/XML B2B) en factura_edi +
  generación de UBL mínimo desde el SNAPSHOT (reutiliza el documento congelado).
- PEPPOL (4.10): SOLO arquitectura (BIS / Access Point / Document Exchange). No envía ni certifica.
"""

import logging
import os

logger = logging.getLogger("facturacion.edi")

FORMATOS = ("ubl", "edifact", "xmlb2b", "peppol")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.facturacion.identidad_facturacion import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()


def registrar_edi(id_factura, formato="ubl", canal=None, estado="preparado", ruta=None,
                  respuesta=None, id_empresa=None) -> int | None:
    """Registra un documento EDI/PEPPOL de la factura (factura_edi) + evento de auditoría."""
    id_empresa = _emp(id_empresa)
    from src.db import facturas_cliente as FC
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO factura_edi (id_empresa, id_factura, formato, canal, estado, "
                        "ruta, respuesta) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_factura, str(formato)[:15], canal, estado, ruta, respuesta))
            eid = cur.lastrowid
            conn.commit()
        ev = "FACTURA_PEPPOL" if formato == "peppol" else "FACTURA_EDI"
        FC.registrar_evento(id_factura, ev, detalle=f"{formato}:{estado}", id_empresa=id_empresa)
        return eid
    except Exception as e:
        logger.error("registrar_edi(%s): %s", id_factura, e); return None


def generar_ubl(id_factura, id_empresa=None) -> str | None:
    """Genera un UBL 2.1 Invoice MÍNIMO desde el snapshot (estructura B2B). Devuelve la ruta."""
    id_empresa = _emp(id_empresa)
    from src.db import facturas_cliente as FC
    snap = FC.obtener_snapshot(id_factura, id_empresa)
    if not snap:
        return None
    fdata = snap.get("factura") or {}
    em = snap.get("emisor") or {}
    cl = snap.get("cliente") or {}
    def esc(s):
        return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lineas = "".join(
        f'<cac:InvoiceLine><cbc:ID>{i+1}</cbc:ID>'
        f'<cbc:LineExtensionAmount currencyID="{esc(snap.get("moneda") or "EUR")}">{it.get("subtotal") or 0}</cbc:LineExtensionAmount>'
        f'<cac:Item><cbc:Name>{esc(it.get("nombre"))}</cbc:Name></cac:Item></cac:InvoiceLine>'
        for i, it in enumerate(snap.get("items") or []))
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
        'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
        'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
        f'<cbc:ID>{esc(fdata.get("numero"))}</cbc:ID>'
        f'<cbc:IssueDate>{esc(fdata.get("fecha_emision"))}</cbc:IssueDate>'
        f'<cbc:DocumentCurrencyCode>{esc(snap.get("moneda") or "EUR")}</cbc:DocumentCurrencyCode>'
        f'<cac:AccountingSupplierParty><cac:Party><cac:PartyName><cbc:Name>{esc(em.get("nombre"))}</cbc:Name></cac:PartyName>'
        f'<cac:PartyTaxScheme><cbc:CompanyID>{esc(em.get("nif"))}</cbc:CompanyID></cac:PartyTaxScheme></cac:Party></cac:AccountingSupplierParty>'
        f'<cac:AccountingCustomerParty><cac:Party><cac:PartyName><cbc:Name>{esc(cl.get("nombre"))}</cbc:Name></cac:PartyName>'
        f'<cac:PartyTaxScheme><cbc:CompanyID>{esc(cl.get("nif"))}</cbc:CompanyID></cac:PartyTaxScheme></cac:Party></cac:AccountingCustomerParty>'
        f'<cac:LegalMonetaryTotal><cbc:PayableAmount currencyID="{esc(snap.get("moneda") or "EUR")}">{fdata.get("total") or 0}</cbc:PayableAmount></cac:LegalMonetaryTotal>'
        f'{lineas}</Invoice>')
    try:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))), "documentos", "EDI")
        os.makedirs(base, exist_ok=True)
        ruta = os.path.join(base, f"{fdata.get('numero') or id_factura}.ubl.xml")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(xml)
        registrar_edi(id_factura, formato="ubl", ruta=ruta, id_empresa=id_empresa)
        return ruta
    except Exception as e:
        logger.error("generar_ubl(%s): %s", id_factura, e); return None


def preparar_peppol(id_factura, id_empresa=None) -> int | None:
    """Prepara (NO envía ni certifica) el documento para PEPPOL BIS vía Access Point. Solo
    arquitectura: registra la intención en factura_edi (formato='peppol')."""
    return registrar_edi(id_factura, formato="peppol", canal="peppol-ap",
                         estado="preparado", id_empresa=id_empresa)
