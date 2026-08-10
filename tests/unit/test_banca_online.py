"""
Tests de BANCA ONLINE (open banking / PSD2, migración 0174).

Sin red ni coste: el transporte HTTP se INYECTA. Verifica la normalización PSD2 (Berlin Group), la
degradación (simulado → 0 movimientos, sin inventar dinero), la credencial CIFRADA y el flujo real de
sincronización (descarga → extracto en el motor de conciliación existente).
"""

import json

import pytest

from src.db import tesoreria as TES
from src.services.banca_online import BancaGateway
from src.services.banca_online import config as CFG
from src.services.banca_online import sync as SYNC
from src.services.banca_online.proveedores import obtener_adaptador, proveedores_con_adaptador
from src.services.banca_online.proveedores.psd2_generico import AdaptadorPSD2


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _cuenta(fab, emp):
    cid = TES.crear_cuenta("Cuenta Banca Test", "ES9121000418450200051332", id_empresa=emp)
    fab._borrar("banca_conexiones", "id_cuenta", cid)
    fab._borrar("cuentas_bancarias", "id", cid)
    return cid


def _transport(status=200, payload=None):
    reg = {}

    def t(metodo, url, headers, params):
        reg.update(metodo=metodo, url=url, headers=headers, params=params)
        return status, json.dumps(payload if payload is not None else {})

    return reg, t


def test_registro_adaptadores():
    assert "psd2_generico" in proveedores_con_adaptador()
    assert obtener_adaptador("banco_x").codigo == "psd2_generico"   # fallback


def test_psd2_normaliza_berlin_group():
    reg, t = _transport(200, {"transactions": {"booked": [
        {"bookingDate": "2026-06-10", "transactionAmount": {"amount": "150.00"},
         "remittanceInformationUnstructured": "Cliente A", "transactionId": "T1"},
        {"bookingDate": "2026-06-11", "transactionAmount": {"amount": "-40.50"}, "transactionId": "T2"}]}})
    movs = AdaptadorPSD2().obtener_movimientos(
        {"endpoint": "https://api.bank/v1", "account_id": "ACC", "credencial": "K"}, None, None, t)
    assert reg["url"] == "https://api.bank/v1/accounts/ACC/transactions"
    assert reg["headers"]["Authorization"] == "Bearer K"
    assert len(movs) == 2 and movs[0]["importe"] == 150.0 and movs[1]["importe"] == -40.5
    assert movs[0]["concepto"] == "Cliente A" and movs[0]["referencia"] == "T1"


def test_psd2_lista_simple():
    _, t = _transport(200, [{"fecha": "2026-01-01", "amount": 10, "concepto": "x", "referencia": "r"}])
    movs = AdaptadorPSD2().obtener_movimientos({"endpoint": "https://x", "account_id": "A"}, None, None, t)
    assert len(movs) == 1 and movs[0]["importe"] == 10.0


def test_gateway_degradable():
    # sin endpoint → simulado aunque se pida real → 0 movimientos (no inventa dinero)
    gw = BancaGateway(proveedor="psd2_generico", endpoint=None, modo_simulado=False)
    assert gw.modo_simulado is True
    assert gw.obtener_movimientos() == []


def test_config_credencial_cifrada(fab, emp, db):
    cta = _cuenta(fab, emp)
    assert CFG.guardar_conexion(cta, proveedor="psd2_generico", endpoint="https://api.bank/v1",
                                account_id="ACC", credencial="TOKENX", modo_simulado=False, id_empresa=emp)
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT credencial_cifrada FROM banca_conexiones WHERE id_empresa=%s AND id_cuenta=%s",
                    (emp, cta))
        raw = cur.fetchone()[0]
    assert raw and "TOKENX" not in str(raw)
    assert CFG.obtener_config(cta, id_empresa=emp, incluir_credencial=True)["_credencial"] == "TOKENX"
    pub = CFG.obtener_config(cta, id_empresa=emp)
    assert "credencial_cifrada" not in pub and "_credencial" not in pub and pub["tiene_credencial"] is True


def test_sync_importa_y_degrada(fab, emp, db):
    cta = _cuenta(fab, emp)
    CFG.guardar_conexion(cta, proveedor="psd2_generico", endpoint="https://api.bank/v1", account_id="ACC",
                         credencial="K", modo_simulado=False, id_empresa=emp)
    _, t = _transport(200, {"transactions": {"booked": [
        {"bookingDate": "2026-06-10", "transactionAmount": {"amount": "150.00"}, "transactionId": "S1"},
        {"bookingDate": "2026-06-11", "transactionAmount": {"amount": "75.00"}, "transactionId": "S2"}]}})
    r = SYNC.sincronizar(cta, id_empresa=emp, transport=t)
    assert r["ok"] and r["importados"] == 2 and r["extracto"]
    fab._borrar("extracto_lineas", "id_extracto", r["extracto"])
    fab._borrar("extractos_bancarios", "id", r["extracto"])
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM extracto_lineas WHERE id_extracto=%s", (r["extracto"],))
        assert cur.fetchone()[0] == 2
    # modo simulado → 0 movimientos, sin extracto
    CFG.guardar_conexion(cta, proveedor="psd2_generico", modo_simulado=True, id_empresa=emp)
    r2 = SYNC.sincronizar(cta, id_empresa=emp)
    assert r2["ok"] and r2["importados"] == 0 and r2["extracto"] is None
