"""
Tesorería · FASE 10 — Integración contable M1 (cobro/pago/transferencia → asiento idempotente).
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import tesoreria as T
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant
from src.services.contabilidad import cuentas as K

E = EMPRESA_DEFAULT_ID
IBAN = "ES9121000418450200051332"
IBAN2 = "DE89370400440532013000"


def _asientos_ref(db, ref):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, total_debe, total_haber FROM contab_asientos "
                    "WHERE id_empresa=%s AND ref_origen=%s AND estado<>'anulado'", (E, ref))
        return [r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))
                for r in cur.fetchall()]


@pytest.fixture(autouse=True)
def _contab_on(db):
    K.activar(E)
    assert K.contabilidad_activa(E)


def test_cobro_genera_asiento_idempotente(db):
    cid = T.crear_cuenta("CB", IBAN, saldo_inicial=0, id_empresa=E)
    try:
        with contexto_tenant(E, None):
            mid = T.registrar_movimiento("COBRO", 121.00, id_cuenta=cid, fecha="2026-06-01", id_empresa=E)
        a = _asientos_ref(db, f"tes:{mid}")
        assert len(a) == 1                              # 1 asiento
        assert float(a[0]["total_debe"]) == 121.0 and float(a[0]["total_haber"]) == 121.0
        # reproceso idempotente: contabilizar de nuevo no crea otro
        from src.services.tesoreria import contabilidad as TC
        with contexto_tenant(E, None):
            TC.contabilizar_movimiento({"id": mid, "tipo": "COBRO", "importe": 121.0,
                                        "id_cuenta": cid, "fecha": "2026-06-01"}, id_empresa=E)
        assert len(_asientos_ref(db, f"tes:{mid}")) == 1
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta=%s", (cid,))
            cur.execute("DELETE FROM cuentas_bancarias WHERE id=%s", (cid,))
            conn.commit()


def test_pago_genera_asiento(db):
    cid = T.crear_cuenta("CP", IBAN, saldo_inicial=500, id_empresa=E)
    try:
        with contexto_tenant(E, None):
            mid = T.registrar_movimiento("PAGO", -80.00, id_cuenta=cid, fecha="2026-06-02", id_empresa=E)
        a = _asientos_ref(db, f"tes:{mid}")
        assert len(a) == 1 and float(a[0]["total_debe"]) == 80.0
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta=%s", (cid,))
            cur.execute("DELETE FROM cuentas_bancarias WHERE id=%s", (cid,))
            conn.commit()


def test_transferencia_genera_un_asiento(db):
    c1 = T.crear_cuenta("O", IBAN, saldo_inicial=300, id_empresa=E)
    c2 = T.crear_cuenta("D", IBAN2, saldo_inicial=0, id_empresa=E)
    try:
        with contexto_tenant(E, None):
            _, _, ref = T.transferencia(c1, c2, 50, fecha="2026-06-03", id_empresa=E)
        a = _asientos_ref(db, f"trf:{ref}")
        assert len(a) == 1 and float(a[0]["total_debe"]) == 50.0
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta IN (%s,%s)", (c1, c2))
            cur.execute("DELETE FROM cuentas_bancarias WHERE id IN (%s,%s)", (c1, c2))
            conn.commit()
