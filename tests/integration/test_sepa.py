"""
Tesorería · FASE 9 — SEPA (mandatos, remesas pain.001/pain.008, estados, validación XSD).
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import sepa as S, tesoreria as T
from src.db.empresa import EMPRESA_DEFAULT_ID
from src.services.tesoreria import sepa as SEPA

E = EMPRESA_DEFAULT_ID
IBAN_EMP = "ES9121000418450200051332"
IBAN_T1 = "DE89370400440532013000"
IBAN_T2 = "FR1420041010050500013M02606"


@pytest.fixture
def cuenta(db):
    cid = T.crear_cuenta("Remesas", IBAN_EMP, bic="CAIXESBBXXX", titular="ACME SL", id_empresa=E)
    yield cid
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cuentas_bancarias WHERE id=%s", (cid,))
        conn.commit()


def _limpia_remesa(db, rid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM remesa_lineas WHERE id_remesa=%s", (rid,))
        cur.execute("DELETE FROM remesas_sepa WHERE id=%s", (rid,))
        conn.commit()


def test_remesa_transferencia_pain001_valida(db, cuenta):
    rid = S.crear_remesa("TRANSFER", id_cuenta=cuenta, id_empresa=E)
    try:
        S.anadir_operacion(rid, "Proveedor A", IBAN_T1, 100.00, concepto="Factura 1",
                           bic="DEUTDEFF", id_empresa=E)
        S.anadir_operacion(rid, "Proveedor B", IBAN_T2, 250.50, concepto="Factura 2", id_empresa=E)
        res = SEPA.generar_xml(rid, id_empresa=E)
        assert res["ok"] and res["xsd_ok"], res.get("errores")
        assert "pain.001.001.03" in res["xml"] and "CstmrCdtTrfInitn" in res["xml"]
        rem = S.obtener_remesa(rid, E)
        assert rem["estado"] == "emitida" and float(rem["importe_total"]) == 350.50
    finally:
        _limpia_remesa(db, rid)


def test_remesa_adeudo_pain008_valida(db, cuenta):
    ref = "MND-" + uuid.uuid4().hex[:8]
    mid = S.crear_mandato(ref, "Cliente X", IBAN_T1, bic="DEUTDEFF", fecha_firma="2026-01-10", id_empresa=E)
    rid = S.crear_remesa("ADEUDO", id_cuenta=cuenta, id_empresa=E)
    try:
        S.anadir_operacion(rid, "Cliente X", IBAN_T1, 60.00, concepto="Cuota", bic="DEUTDEFF",
                           id_mandato=mid, id_empresa=E)
        res = SEPA.generar_xml(rid, id_empresa=E)
        assert res["ok"] and res["xsd_ok"], res.get("errores")
        assert "pain.008.001.02" in res["xml"] and "MndtRltdInf" in res["xml"] and ref in res["xml"]
    finally:
        _limpia_remesa(db, rid)
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM mandatos_sepa WHERE id=%s", (mid,))
            conn.commit()


def test_estados_remesa(db, cuenta):
    rid = S.crear_remesa("TRANSFER", id_cuenta=cuenta, id_empresa=E)
    try:
        S.anadir_operacion(rid, "X", IBAN_T1, 10, id_empresa=E)
        SEPA.generar_xml(rid, id_empresa=E)                 # → emitida
        assert S.cambiar_estado(rid, "aceptada", id_empresa=E)
        assert S.cambiar_estado(rid, "ejecutada", fecha_ejecucion="2026-06-30", id_empresa=E)
        assert S.obtener_remesa(rid, E)["estado"] == "ejecutada"
        with pytest.raises(ValueError):
            S.cambiar_estado(rid, "inventado", id_empresa=E)
    finally:
        _limpia_remesa(db, rid)


def test_iban_invalido_rechaza(db, cuenta):
    rid = S.crear_remesa("TRANSFER", id_cuenta=cuenta, id_empresa=E)
    try:
        with pytest.raises(ValueError):
            S.anadir_operacion(rid, "Malo", "ES0000", 10, id_empresa=E)
    finally:
        _limpia_remesa(db, rid)
