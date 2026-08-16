"""Marketplace + Pagos (F1) — motor PasarelaMarketplace: registro, resolutor y flujo simulado. (unit, sin db)

Cubre: alta en el registry de `stripe_connect` y `simulado_mkt`; el resolutor prioriza Connect si hay
api_key y degrada al simulado si no; el adaptador simulado hace el ciclo completo (onboarding→escrow→
liberación→reembolso) de forma honesta (nunca 'verified' sin KYB) e idempotente por idem_key.
"""

from src.services.pagos_marketplace import psp
from src.services.tpv.pagos.registry import clase_de


def test_adaptadores_registrados():
    assert clase_de("stripe_connect") is not None
    assert clase_de("simulado_mkt") is not None


def test_resolutor_degrada_a_simulado_sin_api_key():
    ad = psp.adaptador(config={})
    assert ad.nombre == "simulado_mkt"
    assert ad.modo() == "simulado"
    assert ad.capacidad_marketplace is True


def test_resolutor_usa_stripe_connect_con_api_key():
    ad = psp.adaptador(config={"api_key": "sk_test_x", "modo": "test"})
    assert ad.nombre == "stripe_connect"
    assert ad.configurado() is True
    assert ad.modo() == "test"


def test_stripe_connect_sin_credenciales_es_degradable():
    cls = clase_de("stripe_connect")
    ad = cls({})
    assert ad.configurado() is False and ad.modo() == "simulado"
    # No lanza: devuelve error controlado.
    r = ad.crear_cuenta_conectada(tipo_parte="proveedor", id_parte=1)
    assert r["ok"] is False


def test_flujo_simulado_completo_honesto():
    ad = psp.adaptador(config={})
    cta = ad.crear_cuenta_conectada(tipo_parte="vendedor", id_parte=9, divisa="EUR")
    assert cta["ok"] and cta["account_id"].startswith("acct_sim_")
    # Honestidad: sin KYB real → pending, sin payouts.
    assert cta["status"] == "pending"
    est = ad.estado_cuenta(cta["account_id"])
    assert est["status"] == "pending" and est["payouts_enabled"] is False

    hold = ad.retener_fondos(importe=100.0, divisa="EUR", vendedor_account=cta["account_id"],
                             comision=10.0, idem_key="op-1")
    assert hold["ok"] and hold["estado"] == "FUNDS_HELD"
    # Idempotencia por idem_key → misma referencia de pago.
    assert ad.retener_fondos(importe=100.0, vendedor_account=cta["account_id"],
                             idem_key="op-1")["payment_ref"] == hold["payment_ref"]

    rel = ad.liberar_fondos(payment_ref=hold["payment_ref"], idem_key="op-1")
    assert rel["ok"] and rel["estado"] == "FUNDS_RELEASED"

    ref = ad.reembolsar(payment_ref=hold["payment_ref"])
    assert ref["ok"] and ref["estado"] == "REFUNDED"
