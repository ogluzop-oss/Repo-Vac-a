"""
Tesorería · FASE 1 — Cuentas bancarias (CRUD, validación IBAN/BIC, cifrado, multiempresa).
"""

import pytest

pytestmark = pytest.mark.db

from src.db import tesoreria as T
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant
from src.utils import iban as IB

E = EMPRESA_DEFAULT_ID
IBAN_OK = "ES9121000418450200051332"     # IBAN de ejemplo válido (mód-97)
IBAN_OK2 = "DE89370400440532013000"


def _limpia(db, cid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cuentas_bancarias WHERE id=%s", (cid,))
        conn.commit()


# ── Validadores IBAN/BIC ──────────────────────────────────────────────────────
def test_validacion_iban_bic():
    assert IB.validar_iban(IBAN_OK)
    assert IB.validar_iban("ES91 2100 0418 4502 0005 1332")   # con espacios
    assert not IB.validar_iban("ES0021000418450200051332")    # control erróneo
    assert not IB.validar_iban("XX12")                         # basura
    assert IB.validar_bic("CAIXESBBXXX") and IB.validar_bic("BSCHESMM")
    assert not IB.validar_bic("123")
    assert IB.mascara_iban(IBAN_OK).startswith("ES**") and IB.mascara_iban(IBAN_OK).endswith("1332")


# ── Alta + cifrado en reposo ──────────────────────────────────────────────────
def test_alta_cuenta_cifra_iban(db):
    with contexto_tenant(E, None):
        cid = T.crear_cuenta("Cuenta Principal", IBAN_OK, titular="ACME SL",
                             bic="CAIXESBBXXX", entidad="CaixaBank")
    assert cid
    try:
        # En la BD el IBAN NO está en claro
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT iban, iban_mascara FROM cuentas_bancarias WHERE id=%s", (cid,))
            raw, mask = cur.fetchone()
        from src.utils import cripto
        if cripto.cifrado_disponible():
            assert raw != IBAN_OK and cripto.parece_cifrado(raw)
        assert mask.endswith("1332")
        # obtener con descifrar=True recupera el IBAN real
        c = T.obtener_cuenta(cid, descifrar=True, id_empresa=E)
        assert IB.normalizar_iban(c["iban"]) == IBAN_OK
        # listado expone solo máscara
        assert all(x["iban"].startswith("ES**") for x in T.listar_cuentas(id_empresa=E) if x["id"] == cid)
    finally:
        _limpia(db, cid)


def test_alta_iban_invalido_rechaza(db):
    with pytest.raises(T.ErrorCuentaBancaria):
        T.crear_cuenta("Mala", "ES0021000418450200051332", id_empresa=E)
    with pytest.raises(T.ErrorCuentaBancaria):
        T.crear_cuenta("Mala BIC", IBAN_OK, bic="XX", id_empresa=E)


# ── Update + baja lógica ──────────────────────────────────────────────────────
def test_update_y_baja(db):
    cid = T.crear_cuenta("C1", IBAN_OK, id_empresa=E)
    try:
        assert T.actualizar_cuenta(cid, nombre_cuenta="C1-bis", iban=IBAN_OK2, id_empresa=E)
        c = T.obtener_cuenta(cid, descifrar=True, id_empresa=E)
        assert c["nombre_cuenta"] == "C1-bis" and IB.normalizar_iban(c["iban"]) == IBAN_OK2
        assert T.desactivar_cuenta(cid, id_empresa=E)
        assert all(x["id"] != cid for x in T.listar_cuentas(id_empresa=E))          # no activas
        assert any(x["id"] == cid for x in T.listar_cuentas(solo_activas=False, id_empresa=E))
    finally:
        _limpia(db, cid)


# ── Aislamiento multiempresa ──────────────────────────────────────────────────
def test_aislamiento_multiempresa(db, fab):
    emp2 = fab.empresa("TES B")
    c1 = T.crear_cuenta("A", IBAN_OK, id_empresa=E)
    c2 = T.crear_cuenta("B", IBAN_OK2, id_empresa=emp2)
    try:
        ids_e = {x["id"] for x in T.listar_cuentas(id_empresa=E)}
        ids_2 = {x["id"] for x in T.listar_cuentas(id_empresa=emp2)}
        assert c1 in ids_e and c1 not in ids_2
        assert c2 in ids_2 and c2 not in ids_e
        assert T.obtener_cuenta(c2, id_empresa=E) is None      # no cruza empresas
    finally:
        _limpia(db, c1); _limpia(db, c2)
