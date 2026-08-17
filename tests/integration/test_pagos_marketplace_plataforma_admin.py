"""Marketplace + Pagos — alta de credenciales Connect de la PLATAFORMA (pantalla de admin). `db`.

Cubre: guardar_config_plataforma persiste (cifrado) clave + webhook + modo + comisión en la fila reservada;
config_plataforma/estado_plataforma los reflejan; el adaptador pasa a Stripe Connect; y las variables de
entorno tienen prioridad sobre lo guardado.
"""

import pytest

from src.services.pagos_marketplace import psp

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _sin_env(monkeypatch):
    for k in ("STRIPE_CONNECT_SECRET_KEY", "STRIPE_PLATFORM_KEY", "STRIPE_CONNECT_WEBHOOK_SECRET",
              "STRIPE_MODE", "MARKETPLACE_FEE_PCT", "STRIPE_COUNTRY"):
        monkeypatch.delenv(k, raising=False)


def _limpia(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM pasarela_config WHERE id_empresa=%s", (psp.TENANT_PLATAFORMA,))
        conn.commit()


def test_alta_y_lectura_credenciales_plataforma(db, fab):
    fab.al_limpiar(lambda: _limpia(db))
    assert psp.guardar_config_plataforma(api_key="sk_test_ADMIN", webhook_secret="whsec_ADMIN",
                                         modo="live", comision_pct=6.5) is True

    cfg = psp.config_plataforma()
    assert cfg["api_key"] == "sk_test_ADMIN"                    # descifrada al leer
    assert cfg["webhook_secret_connect"] == "whsec_ADMIN"
    assert cfg["modo"] == "live" and float(cfg["comision_pct"]) == 6.5
    assert cfg["origen"] == "pasarela_config"

    est = psp.estado_plataforma()
    assert est["configurada"] and est["webhook_configurado"] and est["modo"] == "live"
    assert est["comision_pct"] == 6.5

    # Con credenciales de plataforma → el adaptador es Stripe Connect (no simulado).
    assert psp.adaptador().nombre == "stripe_connect"

    # Guardado parcial: no borra la clave si se pasa api_key=None.
    assert psp.guardar_config_plataforma(modo="test") is True
    assert psp.config_plataforma()["api_key"] == "sk_test_ADMIN" and psp.config_plataforma()["modo"] == "test"


def test_env_tiene_prioridad(db, fab, monkeypatch):
    fab.al_limpiar(lambda: _limpia(db))
    psp.guardar_config_plataforma(api_key="sk_test_DB", modo="test")
    monkeypatch.setenv("STRIPE_CONNECT_SECRET_KEY", "sk_live_ENV")
    cfg = psp.config_plataforma()
    assert cfg["origen"] == "env" and cfg["api_key"] == "sk_live_ENV"
