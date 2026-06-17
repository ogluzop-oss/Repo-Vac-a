"""Integración · C3.4.1 Facturae base: validador XSD + destinatarios/DIR3."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM facturae_destinatarios WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_xsd_facturae_compila_offline():
    """El XSD 3.2.2 compila resolviendo xmldsig al fichero local (sin red)."""
    from src.services.fiscal.facturae import esquemas as E
    assert E.validar(b"<noFacturae/>")[0] is False     # compila y rechaza no-Facturae


def test_destinatario_guardar_obtener(db, fab):
    from src.services.fiscal.facturae import destinatarios as D
    emp = fab.empresa("FE DEST")
    fab.al_limpiar(lambda: _borra(db, emp))
    assert D.guardar("B12345678", id_empresa=emp, razon_social="CLIENTE SL",
                     direccion="Calle 1", cp="28001", municipio="Madrid",
                     provincia="Madrid", es_aapp=0)
    d = D.obtener("B12345678", emp)
    assert d["razon_social"] == "CLIENTE SL" and d["municipio"] == "Madrid"
    # Upsert por (empresa, nif).
    assert D.guardar("B12345678", id_empresa=emp, provincia="Barcelona")
    assert D.obtener("B12345678", emp)["provincia"] == "Barcelona"


def test_destinatario_aislamiento_tenant(db, fab):
    from src.services.fiscal.facturae import destinatarios as D
    a = fab.empresa("FE A"); b = fab.empresa("FE B")
    fab.al_limpiar(lambda: (_borra(db, a), _borra(db, b)))
    D.guardar("B11111111", id_empresa=a, razon_social="A SL")
    assert D.obtener("B11111111", b) is None and D.listar(b) == []
    assert D.obtener("B11111111", a)["razon_social"] == "A SL"


def test_validacion_b2g_detecta_faltantes(db, fab):
    from src.services.fiscal.facturae import destinatarios as D
    emp = fab.empresa("FE B2G")
    fab.al_limpiar(lambda: _borra(db, emp))
    # AAPP sin DIR3 ni dirección completa → faltan campos.
    D.guardar("P2800000B", id_empresa=emp, razon_social="AYUNTAMIENTO", es_aapp=1)
    faltan = D.validar_para_b2g(D.obtener("P2800000B", emp))
    assert "direccion" in faltan and "dir3_oficina_contable" in faltan
    # Completo → sin faltantes.
    D.guardar("P2800000B", id_empresa=emp, razon_social="AYUNTAMIENTO", es_aapp=1,
              direccion="Plaza 1", cp="28001", municipio="Madrid", provincia="Madrid",
              dir3_oficina_contable="L01280796", dir3_organo_gestor="L01280796",
              dir3_unidad_tramitadora="L01280796")
    assert D.validar_para_b2g(D.obtener("P2800000B", emp)) == []
