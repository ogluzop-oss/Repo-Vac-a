"""Unit · serialización XML Verifactu (estructura provisional, sin BD)."""

from xml.etree import ElementTree as ET

import pytest

pytestmark = pytest.mark.unit


def _fila(tipo="ticket", kind="alta", hash_anterior=None):
    import json
    meta = {"kind": kind, "tipo_factura": "F2", "nif_emisor": "B12345678",
            "fecha_expedicion": "16-06-2026", "fecha_gen": "2026-06-16T10:00:00+02:00",
            "cuota_total": "2.10", "importe_total": "12.10",
            "num_serie_anulada": "A/3"}
    return {"serie": "A", "numero": 1, "tipo": tipo, "hash": "ABC", "payload": json.dumps(meta),
            "hash_anterior": hash_anterior}


def test_registro_alta_xml_bien_formado_y_con_datos():
    from src.services.fiscal import verifactu_xml as vx
    xml = vx.registro_xml(_fila())
    root = ET.fromstring(xml)                  # debe ser XML válido
    assert root.tag == "RegistroAlta"
    assert root.findtext("NumSerieFactura") == "A/1"
    assert root.findtext("ImporteTotal") == "12.10"
    assert root.findtext("Huella") == "ABC"
    assert root.find("SistemaInformatico") is not None
    assert root.findtext("PrimerRegistro") == "S"   # sin hash anterior


def test_registro_con_encadenamiento():
    from src.services.fiscal import verifactu_xml as vx
    root = ET.fromstring(vx.registro_xml(_fila(hash_anterior="PREV")))
    ant = root.find("RegistroAnterior")
    assert ant is not None and ant.findtext("Huella") == "PREV"


def test_registro_anulacion_xml():
    from src.services.fiscal import verifactu_xml as vx
    root = ET.fromstring(vx.registro_xml(_fila(tipo="anulacion", kind="anulacion")))
    assert root.tag == "RegistroAnulacion"
    assert root.findtext("NumSerieFacturaAnulada") == "A/3"


def test_lote_xml_agrupa():
    from src.services.fiscal import verifactu_xml as vx
    root = ET.fromstring(vx.lote_xml([_fila(), _fila()]))
    assert root.tag == "RegFactuSistemaFacturacion"
    assert len(root.find("RegistroFactura").findall("RegistroAlta")) == 2
