"""Unit · XML Verifactu CONFORME al XSD oficial (espejo), sin BD."""

import json

import pytest

pytestmark = pytest.mark.unit

from src.services.fiscal.esquemas import NS

_SF = "{%s}" % NS["sf"]


def _fila(tipo="ticket", kind="alta", numero=1, hash_anterior=None):
    meta = {
        "kind": kind, "tipo_factura": "F2" if tipo == "ticket" else "F1",
        "nif_emisor": "B12345678", "nombre_emisor": "DEMO SL", "descripcion": "Venta",
        "fecha_expedicion": "16-06-2026", "fecha_gen": "2026-06-16T10:00:00+02:00",
        "cuota_total": "2.10", "importe_total": "12.10",
        "num_serie_anulada": "A/3",
        "desglose": [{"clave_regimen": "01", "calificacion": "S1", "tipo": "21.00",
                      "base": "10.00", "cuota": "2.10"}],
    }
    return {"id_empresa": "e1", "serie": "A", "numero": numero, "tipo": tipo,
            "hash": "A" * 64, "hash_anterior": hash_anterior, "payload": json.dumps(meta)}


def test_alta_valida_contra_xsd():
    from src.services.fiscal import verifactu_xml as vx
    ok, err = vx.validar(vx.lote_xml([_fila()]))
    assert ok, err


def test_anulacion_valida_contra_xsd():
    from src.services.fiscal import verifactu_xml as vx
    ok, err = vx.validar(vx.lote_xml([_fila(tipo="anulacion", kind="anulacion")]))
    assert ok, err


def test_estructura_namespaces_y_datos():
    from lxml import etree
    from src.services.fiscal import verifactu_xml as vx
    root = etree.fromstring(vx.lote_xml([_fila()]))
    # IDFactura anidado, en namespace sf, con NumSerieFactura = serie/numero.
    ns = {"sf": NS["sf"]}
    assert root.find(".//sf:IDFactura/sf:NumSerieFactura", ns).text == "A/1"
    assert root.find(".//sf:NombreRazonEmisor", ns).text == "DEMO SL"
    assert root.find(".//sf:Desglose/sf:DetalleDesglose/sf:BaseImponibleOimporteNoSujeto", ns).text == "10.00"
    assert root.find(".//sf:Encadenamiento/sf:PrimerRegistro", ns).text == "S"
    sif = root.find(".//sf:SistemaInformatico", ns)
    assert sif.find("sf:TipoUsoPosibleSoloVerifactu", ns).text == "S"


def test_encadenamiento_registro_anterior(monkeypatch):
    from lxml import etree
    from src.services.fiscal import verifactu_xml as vx
    # Simula el registro anterior (numero 1) para construir RegistroAnterior.
    anterior = _fila(numero=1)
    monkeypatch.setattr("src.db.fiscal.obtener_por_serie_numero",
                        lambda emp, serie, numero: anterior)
    root = etree.fromstring(vx.lote_xml([_fila(numero=2, hash_anterior="B" * 64)]))
    ns = {"sf": NS["sf"]}
    ra = root.find(".//sf:Encadenamiento/sf:RegistroAnterior", ns)
    assert ra is not None
    assert ra.find("sf:NumSerieFactura", ns).text == "A/1"
    assert ra.find("sf:Huella", ns).text == "B" * 64


def test_lote_multiple_valida(monkeypatch):
    from src.services.fiscal import verifactu_xml as vx
    monkeypatch.setattr("src.db.fiscal.obtener_por_serie_numero",
                        lambda emp, serie, numero: _fila(numero=numero))
    ok, err = vx.validar(vx.lote_xml([_fila(numero=1), _fila(numero=2, hash_anterior="B" * 64)]))
    assert ok, err
