"""Unit · serializador Facturae 3.2.x CONFORME al XSD oficial (espejo), sin BD."""

import pytest

pytestmark = pytest.mark.unit

_EMISOR = {"nif": "A12345674", "razon_social": "EMISOR SL", "persona": "J",
           "residencia": "R", "direccion": "Calle 1", "cp": "28001",
           "municipio": "Madrid", "provincia": "Madrid", "cod_pais": "ESP"}
_RECEPTOR = {"nif": "B12345678", "razon_social": "CLIENTE SL", "persona": "J",
             "residencia": "R", "direccion": "Calle 2", "cp": "08001",
             "municipio": "Barcelona", "provincia": "Barcelona", "cod_pais": "ESP"}


def _datos(lineas=None):
    from src.services.fiscal.facturae import facturae_xml as FX
    lineas = lineas or [{"descripcion": "Producto X", "cantidad": 2, "subtotal": 24.20, "iva": 21.0}]
    return FX.normalizar(_EMISOR, _RECEPTOR, lineas, numero="FAC/1", fecha="2026-06-16")


def test_facturae_valida_xsd():
    from src.services.fiscal.facturae import esquemas as E, facturae_xml as FX
    ok, err = E.validar(FX.facturae_xml(_datos()), "3.2.2")
    assert ok, err


def test_facturae_multitipo_iva_valida():
    from src.services.fiscal.facturae import esquemas as E, facturae_xml as FX
    datos = _datos([{"descripcion": "A", "cantidad": 1, "subtotal": 12.10, "iva": 21.0},
                    {"descripcion": "B", "cantidad": 1, "subtotal": 11.00, "iva": 10.0}])
    assert datos["totales"]["cuota"] == 3.1               # 2.10 + 1.00
    ok, err = E.validar(FX.facturae_xml(datos), "3.2.2")
    assert ok, err


def test_facturae_receptor_persona_fisica():
    from src.services.fiscal.facturae import esquemas as E, facturae_xml as FX
    rec = {**_RECEPTOR, "persona": "F", "razon_social": "Juan Pérez García"}
    datos = FX.normalizar(_EMISOR, rec, [{"descripcion": "X", "cantidad": 1, "subtotal": 12.10, "iva": 21.0}],
                          numero="FAC/2", fecha="2026-06-16")
    xml = FX.facturae_xml(datos)
    ok, err = E.validar(xml, "3.2.2")
    assert ok, err
    assert b"<Individual>" in xml and b"<FirstSurname>" in xml


def test_estructura_unqualified_raiz_namespaced():
    from lxml import etree
    from src.services.fiscal.facturae import NS_FACTURAE, facturae_xml as FX
    root = etree.fromstring(FX.facturae_xml(_datos()))
    assert root.tag == "{%s}Facturae" % NS_FACTURAE["3.2.2"]
    # Hijos sin namespace (unqualified).
    assert root.find("FileHeader") is not None
    assert root.find("Invoices/Invoice/InvoiceTotals/InvoiceTotal").text == "24.20"
