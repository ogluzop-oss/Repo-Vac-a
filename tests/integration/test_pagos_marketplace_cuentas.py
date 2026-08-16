"""Marketplace + Pagos (F0) — cuentas conectadas del PSP (modelo tokenizado). `db`.

Cubre: onboarding degradado a SIMULADO (nunca 'verified' sin acuse real), guardado del token opaco +
metadatos (sin IBAN), sincronización desde webhook (`account.updated`) y resumen para la UI.
"""

import pytest

from src.services.pagos_marketplace import cuentas as CU

pytestmark = pytest.mark.db


def _limpia(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM psp_cuentas_conectadas WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_onboarding_simulado_y_resumen(db, fab):
    emp = fab.empresa("EMP psp onboarding")
    fab.al_limpiar(lambda: _limpia(db, emp))

    # Sin PSP configurado → degrada a simulado: account_id de prueba, estado 'pending' (jamás 'verified').
    r = CU.crear_onboarding("proveedor", 77, divisa="EUR", id_empresa=emp)
    assert r["ok"] and r["modo"] == "simulado"
    assert r["account_id"].startswith("acct_sim_")
    assert r["status"] == "pending"

    res = CU.resumen("proveedor", 77, emp)
    assert res is not None
    assert res["account_id"] == r["account_id"]
    assert res["status"] == "pending"
    assert res["payouts_enabled"] is False
    # Sin metadatos aún → etiqueta genérica (nunca expone IBAN).
    assert res["etiqueta"] == "Cuenta bancaria"


def test_sincronizar_estado_desde_webhook(db, fab):
    emp = fab.empresa("EMP psp sync")
    fab.al_limpiar(lambda: _limpia(db, emp))
    r = CU.crear_onboarding("vendedor", 5, divisa="EUR", id_empresa=emp)
    acct = r["account_id"]

    # El PSP valida KYB y notifica por webhook: verified + payouts + banco/últimos4.
    assert CU.sincronizar_estado(acct, status="verified", payouts_enabled=True, charges_enabled=True,
                                 banco="CaixaBank", ultimos4="1332") is True

    res = CU.resumen("vendedor", 5, emp)
    assert res["status"] == "verified" and res["payouts_enabled"] is True
    assert res["ultimos4"] == "1332" and res["banco"] == "CaixaBank"
    assert res["etiqueta"] == "CaixaBank ···1332"
    # Localización por token (la usa el webhook).
    assert CU.cuenta_por_account_id(acct)["id_empresa"] == emp


def test_registrar_token_idempotente(db, fab):
    emp = fab.empresa("EMP psp idem")
    fab.al_limpiar(lambda: _limpia(db, emp))
    a = CU.registrar_token("empresa", 0, "acct_LIVE_1", psp="stripe", status="pending", id_empresa=emp)
    b = CU.registrar_token("empresa", 0, "acct_LIVE_1", psp="stripe", status="verified",
                           payouts_enabled=True, banco="BBVA", ultimos4="9000", id_empresa=emp)
    assert a["ok"] and b["ok"]
    res = CU.resumen("empresa", 0, emp)
    # Upsert (no duplica): refleja el último estado.
    assert res["status"] == "verified" and res["payouts_enabled"] is True and res["ultimos4"] == "9000"
