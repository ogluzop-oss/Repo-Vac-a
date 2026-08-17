"""Marketplace + Pagos — credenciales Connect de la PLATAFORMA (P1). (unit, sin db)

Cubre: `config_plataforma` lee de variables de entorno del operador; el resolutor usa Stripe Connect cuando
hay credenciales de plataforma y degrada al simulado cuando no; la comisión es un ajuste de plataforma.
"""

import pytest

from src.services.pagos_marketplace import psp


@pytest.fixture(autouse=True)
def _sin_env(monkeypatch):
    for k in ("STRIPE_CONNECT_SECRET_KEY", "STRIPE_PLATFORM_KEY", "STRIPE_CONNECT_WEBHOOK_SECRET",
              "STRIPE_MODE", "MARKETPLACE_FEE_PCT", "STRIPE_COUNTRY"):
        monkeypatch.delenv(k, raising=False)


def test_config_plataforma_desde_env(monkeypatch):
    monkeypatch.setenv("STRIPE_CONNECT_SECRET_KEY", "sk_live_platform")
    monkeypatch.setenv("STRIPE_CONNECT_WEBHOOK_SECRET", "whsec_connect")
    monkeypatch.setenv("STRIPE_MODE", "live")
    monkeypatch.setenv("MARKETPLACE_FEE_PCT", "7.5")
    cfg = psp.config_plataforma()
    assert cfg["proveedor"] == "stripe_connect" and cfg["api_key"] == "sk_live_platform"
    assert cfg["webhook_secret_connect"] == "whsec_connect" and cfg["modo"] == "live"
    assert cfg["comision_pct"] == 7.5 and cfg["origen"] == "env"


def test_adaptador_usa_connect_con_credenciales_de_plataforma(monkeypatch):
    monkeypatch.setenv("STRIPE_CONNECT_SECRET_KEY", "sk_test_platform")
    ad = psp.adaptador()
    assert ad.nombre == "stripe_connect" and ad.configurado() is True


def test_adaptador_degrada_a_simulado_sin_plataforma(monkeypatch):
    # Sin env y sin fila de plataforma → config vacía → simulado.
    monkeypatch.setattr(psp, "config_plataforma", lambda: {})
    ad = psp.adaptador()
    assert ad.nombre == "simulado_mkt" and ad.modo() == "simulado"


def test_override_config_explicito_para_test(monkeypatch):
    # `config=` explícito tiene prioridad (no toca env ni BD).
    ad = psp.adaptador(config={"api_key": "sk_test_x"})
    assert ad.nombre == "stripe_connect" and ad.configurado() is True
