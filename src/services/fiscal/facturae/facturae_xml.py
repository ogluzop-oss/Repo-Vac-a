"""
Serializador Facturae 3.2.x (C3.4.2) — CONFORME al XSD oficial.

Mapea emisor/receptor/líneas/impuestos/totales a XML Facturae (unqualified salvo la
raíz, peculiaridad del esquema). stdlib en runtime; validación XSD con lxml en
tests/build (`facturae.esquemas.validar`). El IVA se deriva con `utils.fiscalidad`
(reutilización). La firma XAdES se aplica después (C3.4.3).
"""

import logging
import xml.etree.ElementTree as ET

from src.services.fiscal.facturae import NS_FACTURAE, VERSION_DEFECTO

logger = logging.getLogger("fiscal.facturae.xml")


def _e(parent, tag, text=None):
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def _imp(v) -> str:
    return f"{round(float(v or 0), 2):.2f}"


def _centros_administrativos(parent, centros: list):
    """AdministrativeCentres (DIR3) para B2G/FACe. Roles: 01 oficina contable,
    02 órgano gestor, 03 unidad tramitadora."""
    ac = _e(parent, "AdministrativeCentres")
    for c in centros:
        ce = _e(ac, "AdministrativeCentre")
        _e(ce, "CentreCode", c.get("code"))
        _e(ce, "RoleTypeCode", c.get("role"))
        _e(ce, "Name", c.get("name") or c.get("role"))
        ad = _e(ce, "AddressInSpain")
        _e(ad, "Address", c.get("direccion") or "-")
        _e(ad, "PostCode", c.get("cp") or "00000")
        _e(ad, "Town", c.get("municipio") or "-")
        _e(ad, "Province", c.get("provincia") or "-")
        _e(ad, "CountryCode", "ESP")


def _parte(parent, tag, p: dict):
    """SellerParty/BuyerParty: TaxIdentification + (AdministrativeCentres DIR3) +
    LegalEntity (J) o Individual (F)."""
    parte = _e(parent, tag)
    ti = _e(parte, "TaxIdentification")
    _e(ti, "PersonTypeCode", p.get("persona") or "J")
    _e(ti, "ResidenceTypeCode", p.get("residencia") or "R")
    _e(ti, "TaxIdentificationNumber", p.get("nif") or "")
    if p.get("centros"):                       # DIR3 (va antes de LegalEntity en BusinessType)
        _centros_administrativos(parte, p["centros"])
    if (p.get("persona") or "J") == "F":
        ind = _e(parte, "Individual")
        nombre = (p.get("razon_social") or "").split()
        _e(ind, "Name", nombre[0] if nombre else (p.get("razon_social") or ""))
        _e(ind, "FirstSurname", " ".join(nombre[1:]) or "-")
        _dir(ind, p)
    else:
        le = _e(parte, "LegalEntity")
        _e(le, "CorporateName", p.get("razon_social") or "")
        _dir(le, p)


def _dir(parent, p: dict):
    """Dirección: AddressInSpain (ESP) u OverseasAddress (extranjero)."""
    if (p.get("cod_pais") or "ESP") == "ESP":
        ad = _e(parent, "AddressInSpain")
        _e(ad, "Address", p.get("direccion") or "")
        _e(ad, "PostCode", p.get("cp") or "")
        _e(ad, "Town", p.get("municipio") or "")
        _e(ad, "Province", p.get("provincia") or "")
        _e(ad, "CountryCode", "ESP")
    else:
        ad = _e(parent, "OverseasAddress")
        _e(ad, "Address", p.get("direccion") or "")
        _e(ad, "PostCodeAndTown", f"{p.get('cp') or ''} {p.get('municipio') or ''}".strip())
        _e(ad, "Province", p.get("provincia") or "")
        _e(ad, "CountryCode", p.get("cod_pais") or "")


def _taxes_outputs(parent, desglose: list):
    to = _e(parent, "TaxesOutputs")
    for d in desglose:
        tax = _e(to, "Tax")
        _e(tax, "TaxTypeCode", "01")                 # 01 = IVA
        _e(tax, "TaxRate", _imp(d.get("tipo")))
        tb = _e(tax, "TaxableBase"); _e(tb, "TotalAmount", _imp(d.get("base")))
        ta = _e(tax, "TaxAmount"); _e(ta, "TotalAmount", _imp(d.get("cuota")))


def normalizar(emisor: dict, receptor: dict, lineas_pvp: list, numero, fecha,
               id_empresa=None, moneda="EUR", version=VERSION_DEFECTO) -> dict:
    """Construye los datos normalizados (con desglose de IVA) a partir de líneas en
    PVP (IVA incluido). Reutiliza `utils.fiscalidad`."""
    from src.utils import fiscalidad
    lineas, por_tipo = [], {}
    for ln in lineas_pvp:
        cant = float(ln.get("cantidad") or 1)
        pvp_total = round(float(ln.get("subtotal") if ln.get("subtotal") is not None
                                else (ln.get("precio") or 0) * cant), 2)
        d = fiscalidad.desglose_iva(pvp_total, id_empresa=id_empresa,
                                    tipo=ln.get("iva"))
        base, cuota, tipo = d["base"], d["cuota"], d["tipo"]
        lineas.append({"descripcion": ln.get("descripcion") or ln.get("nombre") or "",
                       "cantidad": cant, "precio_unit": round(base / cant, 6) if cant else base,
                       "base": base, "cuota": cuota, "tipo_iva": tipo})
        acc = por_tipo.setdefault(tipo, {"tipo": tipo, "base": 0.0, "cuota": 0.0})
        acc["base"] += base; acc["cuota"] += cuota
    for a in por_tipo.values():
        a["base"] = round(a["base"], 2); a["cuota"] = round(a["cuota"], 2)
    base_t = round(sum(l["base"] for l in lineas), 2)
    cuota_t = round(sum(l["cuota"] for l in lineas), 2)
    return {"version": version, "moneda": moneda, "numero": str(numero), "fecha": fecha,
            "emisor": emisor, "receptor": receptor, "lineas": lineas,
            "desglose": list(por_tipo.values()),
            "totales": {"base": base_t, "cuota": cuota_t, "total": round(base_t + cuota_t, 2)}}


def facturae_xml(datos: dict) -> bytes:
    """XML Facturae a partir de datos normalizados. Conforme a Facturaev3_2_x.xsd."""
    version = datos.get("version", VERSION_DEFECTO)
    ns = NS_FACTURAE.get(version, NS_FACTURAE[VERSION_DEFECTO])
    tot = datos["totales"]
    root = ET.Element("{%s}Facturae" % ns)

    fh = _e(root, "FileHeader")
    _e(fh, "SchemaVersion", version)
    _e(fh, "Modality", "I")
    _e(fh, "InvoiceIssuerType", "EM")
    b = _e(fh, "Batch")
    _e(b, "BatchIdentifier", f"{datos.get('numero')}")
    _e(b, "InvoicesCount", "1")
    _e(_e(b, "TotalInvoicesAmount"), "TotalAmount", _imp(tot["total"]))
    _e(_e(b, "TotalOutstandingAmount"), "TotalAmount", _imp(tot["total"]))
    _e(_e(b, "TotalExecutableAmount"), "TotalAmount", _imp(tot["total"]))
    _e(b, "InvoiceCurrencyCode", datos.get("moneda", "EUR"))

    parties = _e(root, "Parties")
    _parte(parties, "SellerParty", datos["emisor"])
    _parte(parties, "BuyerParty", datos["receptor"])

    inv = _e(_e(root, "Invoices"), "Invoice")
    ih = _e(inv, "InvoiceHeader")
    _e(ih, "InvoiceNumber", datos.get("numero"))
    if datos.get("serie"):
        _e(ih, "InvoiceSeriesCode", datos["serie"])
    _e(ih, "InvoiceDocumentType", datos.get("tipo_documento", "FC"))   # FC factura completa
    _e(ih, "InvoiceClass", datos.get("clase", "OO"))                   # OO original
    iss = _e(inv, "InvoiceIssueData")
    _e(iss, "IssueDate", datos.get("fecha"))
    _e(iss, "InvoiceCurrencyCode", datos.get("moneda", "EUR"))
    _e(iss, "TaxCurrencyCode", datos.get("moneda", "EUR"))
    _e(iss, "LanguageName", "es")
    _taxes_outputs(inv, datos["desglose"])
    it = _e(inv, "InvoiceTotals")
    _e(it, "TotalGrossAmount", _imp(tot["base"]))
    _e(it, "TotalGrossAmountBeforeTaxes", _imp(tot["base"]))
    _e(it, "TotalTaxOutputs", _imp(tot["cuota"]))
    _e(it, "TotalTaxesWithheld", "0.00")
    _e(it, "InvoiceTotal", _imp(tot["total"]))
    _e(it, "TotalOutstandingAmount", _imp(tot["total"]))
    _e(it, "TotalExecutableAmount", _imp(tot["total"]))
    items = _e(inv, "Items")
    for l in datos["lineas"]:
        line = _e(items, "InvoiceLine")
        _e(line, "ItemDescription", l["descripcion"])
        _e(line, "Quantity", f"{l['cantidad']:g}")
        _e(line, "UnitOfMeasure", "01")
        _e(line, "UnitPriceWithoutTax", f"{round(float(l['precio_unit']), 6):.6f}")
        _e(line, "TotalCost", _imp(l["base"]))
        _e(line, "GrossAmount", _imp(l["base"]))
        _taxes_outputs(line, [{"tipo": l["tipo_iva"], "base": l["base"], "cuota": l["cuota"]}])
    return ET.tostring(root, encoding="utf-8")
