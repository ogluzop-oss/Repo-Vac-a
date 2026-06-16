"""Integración · evidencias fiscales (C3.2): fichero + índice en centro documental."""

import os

import pytest

pytestmark = pytest.mark.db


def _borra_fiscal(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("fiscal_cola", "fiscal_registros", "fiscal_config"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM documentos_registro WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_evidencia_xml_va_a_fichero_y_centro_documental(db, fab):
    from src.db import documentos as D
    from src.db.empresa import contexto_tenant
    from src.services.fiscal import proveedor_fiscal_actual
    from src.services.fiscal.evidencias import guardar_evidencia
    emp = fab.empresa("FISCAL EVID")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    with contexto_tenant(emp, None):
        reg = proveedor_fiscal_actual().registrar("factura", referencia="F1", total=42.0)
        ev = guardar_evidencia(reg, "xml", "<Factura>demo</Factura>", id_empresa=emp)
    assert ev and os.path.exists(ev["ruta"])          # artefacto en disco
    assert len(ev["hash"]) == 64
    # Indexado en el centro documental (solo referencia + hash + metadatos).
    docs = D.listar_documentos(id_empresa=emp, referencia=ev["referencia"])
    assert docs and docs[0]["hash_documental"] == ev["hash"]
    assert docs[0]["tipo_documento"] == "factura"
    os.remove(ev["ruta"])


def test_evidencia_no_guarda_binario_en_bd_fiscal(db, fab):
    """La tabla fiscal_registros no almacena el artefacto, solo refs/metadatos."""
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal import proveedor_fiscal_actual
    from src.services.fiscal.evidencias import guardar_evidencia
    emp = fab.empresa("FISCAL EVID2")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    with contexto_tenant(emp, None):
        reg = proveedor_fiscal_actual().registrar("factura", referencia="F2", total=10.0)
        ev = guardar_evidencia(reg, "firma", b"\x01\x02FIRMA", extension="p7s", id_empresa=emp)
    r = F.listar_registros(id_empresa=emp)[0]
    assert "FIRMA" not in (r.get("payload") or "")    # el binario no está en la BD fiscal
    assert os.path.exists(ev["ruta"])
    os.remove(ev["ruta"])
