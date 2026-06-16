"""Unit · formato legal Verifactu (huella, nº serie, QR) — funciones puras, sin BD."""

import pytest

pytestmark = pytest.mark.unit

_CAMPOS = {
    "IDEmisorFactura": "B12345678", "NumSerieFactura": "A/1",
    "FechaExpedicionFactura": "16-06-2026", "TipoFactura": "F2",
    "CuotaTotal": "2.10", "ImporteTotal": "12.10",
    "FechaHoraHusoGenRegistro": "2026-06-16T10:00:00+02:00",
}


def test_huella_alta_formato_y_encadenado():
    from src.services.fiscal import verifactu_legal as L
    h1 = L.huella_alta(_CAMPOS, None)
    h2 = L.huella_alta({**_CAMPOS, "NumSerieFactura": "A/2"}, h1)
    assert len(h1) == 64 and h1 == h1.upper()        # SHA-256 hex MAYÚSCULAS
    assert h1 != h2
    # La huella depende de la anterior (encadenado legal).
    assert L.huella_alta(_CAMPOS, "OTRA") != h1


def test_huella_es_concatenacion_clave_valor_ordenada():
    import hashlib
    from src.services.fiscal import verifactu_legal as L
    esperado_cad = ("IDEmisorFactura=B12345678&NumSerieFactura=A/1&"
                    "FechaExpedicionFactura=16-06-2026&TipoFactura=F2&"
                    "CuotaTotal=2.10&ImporteTotal=12.10&Huella=&"
                    "FechaHoraHusoGenRegistro=2026-06-16T10:00:00+02:00")
    esperado = hashlib.sha256(esperado_cad.encode()).hexdigest().upper()
    assert L.huella_alta(_CAMPOS, None) == esperado


def test_num_serie_y_qr_entornos():
    from src.services.fiscal import verifactu_legal as L
    assert L.num_serie("A-T1", 7) == "A-T1/7"
    qr_pre = L.contenido_qr("B1", "A/1", "16-06-2026", "12.10", entorno="preproduccion")
    qr_pro = L.contenido_qr("B1", "A/1", "16-06-2026", "12.10", entorno="produccion")
    assert qr_pre.startswith("https://prewww2.aeat.es") and "nif=B1" in qr_pre
    assert qr_pro.startswith("https://www2.agenciatributaria.es")   # host oficial del QR
    assert "numserie=A%2F1" in qr_pre and "importe=12.10" in qr_pre


def test_campos_anulacion_usa_factura_anulada():
    from src.services.fiscal import verifactu_legal as L
    c = L.campos_anulacion("A", 5, {"nif_emisor": "B1", "num_serie_anulada": "A/3",
                                    "fecha_expedicion": "16-06-2026",
                                    "fecha_gen": "2026-06-16T10:00:00+02:00"})
    assert c["NumSerieFacturaAnulada"] == "A/3" and "ImporteTotal" not in c
