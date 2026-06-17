"""Integración · C3.4.6 conformidad Facturae: casos válidos contra el XSD oficial."""

import pytest

pytestmark = pytest.mark.db

_EMISOR = {"nif": "A12345674", "razon_social": "EMISOR SL", "persona": "J", "residencia": "R",
           "direccion": "C1", "cp": "28001", "municipio": "Madrid", "provincia": "Madrid", "cod_pais": "ESP"}


def _datos(receptor, lineas=None):
    from src.services.fiscal.facturae import facturae_xml as FX
    lineas = lineas or [{"descripcion": "X", "cantidad": 1, "subtotal": 12.10, "iva": 21.0}]
    return FX.normalizar(_EMISOR, receptor, lineas, numero="1", fecha="2026-06-16")


def _valida(datos):
    from src.services.fiscal.facturae import esquemas as E, facturae_xml as FX
    return E.validar(FX.facturae_xml(datos), "3.2.2")


def test_b2g_con_dir3_valida_y_contiene_centros():
    receptor = {"nif": "P2800000B", "razon_social": "AYUNTAMIENTO", "persona": "J",
                "residencia": "R", "direccion": "Plaza 1", "cp": "28001", "municipio": "Madrid",
                "provincia": "Madrid", "cod_pais": "ESP",
                "centros": [{"code": "L01280796", "role": "01", "name": "OC"},
                            {"code": "L01280796", "role": "02", "name": "OG"},
                            {"code": "L01280796", "role": "03", "name": "UT"}]}
    from src.services.fiscal.facturae import facturae_xml as FX
    xml = FX.facturae_xml(_datos(receptor))
    from src.services.fiscal.facturae import esquemas as E
    ok, err = E.validar(xml, "3.2.2")
    assert ok, err
    assert b"AdministrativeCentres" in xml and b"<RoleTypeCode>03</RoleTypeCode>" in xml


def test_b2b_persona_juridica_valida():
    receptor = {"nif": "B12345678", "razon_social": "CLIENTE SL", "persona": "J", "residencia": "R",
                "direccion": "C2", "cp": "08001", "municipio": "Barcelona", "provincia": "Barcelona",
                "cod_pais": "ESP"}
    ok, err = _valida(_datos(receptor)); assert ok, err


def test_multitipo_iva_valida_3_2_1():
    """Conformidad también contra 3.2.1 (compatibilidad de versión)."""
    from src.services.fiscal.facturae import esquemas as E, facturae_xml as FX
    receptor = {"nif": "B12345678", "razon_social": "CLIENTE SL", "persona": "J", "residencia": "R",
                "direccion": "C2", "cp": "08001", "municipio": "Barcelona", "provincia": "Barcelona",
                "cod_pais": "ESP"}
    datos = FX.normalizar(_EMISOR, receptor,
                          [{"descripcion": "A", "cantidad": 1, "subtotal": 12.10, "iva": 21.0},
                           {"descripcion": "B", "cantidad": 1, "subtotal": 11.00, "iva": 10.0}],
                          numero="1", fecha="2026-06-16", version="3.2.1")
    ok, err = E.validar(FX.facturae_xml(datos), "3.2.1"); assert ok, err


def test_receptor_dir3_desde_destinatario(db, fab):
    """El servicio construye los centros DIR3 desde facturae_destinatarios (es_aapp)."""
    from src.services.fiscal.facturae import destinatarios as D, servicio
    emp = fab.empresa("FE CONF DIR3")
    def _borra():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM facturae_destinatarios WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,)); conn.commit()
    fab.al_limpiar(_borra)
    D.guardar("P2800000B", id_empresa=emp, razon_social="AYTO", es_aapp=1, direccion="Plaza 1",
              cp="28001", municipio="Madrid", provincia="Madrid",
              dir3_oficina_contable="L01280796", dir3_organo_gestor="L01280796",
              dir3_unidad_tramitadora="L01280796")
    rec, err = servicio._receptor({"cliente_nif": "P2800000B"}, emp)
    assert err is None and len(rec["centros"]) == 3
    assert {c["role"] for c in rec["centros"]} == {"01", "02", "03"}
