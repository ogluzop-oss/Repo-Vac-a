"""
Tests · Fase WEB-17 — Conector PrestaShop real (mismo patrón que WooCommerce/Shopify).

Verifica: registro en el motor WEB-13 (intacto), autenticación/validación, importación productos/clientes/
pedidos (reutiliza motores ERP), exportación stock/precios, sincronización inicial/incremental, idempotencia/
sin duplicados, auditoría PRESTA_*, secretos por SecretManager, multiempresa, y aparición automática en el
Centro (WEB-16.5 sin cambios). Sin red (transporte inyectado).
"""

import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")

from src.services.marketplace import integraciones_comerciales as ic  # noqa: E402
from src.services.marketplace.integraciones_comerciales.prestashop import (  # noqa: E402
    secretos as S, transporte as T)


class _FakePresta:
    def __init__(self, order_id=None):
        self.puts = []
        self.order_id = order_id if order_id is not None else random.randint(10_000_000, 99_999_999)

    def request(self, method, base_url, path, *, api_key=None, json=None, params=None):
        assert api_key
        off = int((params or {}).get("limit", "0,1").split(",")[0]) if params and "limit" in params else 0
        if path == "configurations":
            return {"configurations": [{"value": "8.1.2"}]}
        if path == "products":
            return {"products": [] if off else [
                {"id": 1, "reference": "ART001", "name": [{"id": 1, "value": "Prod 1"}], "price": "9.90"}]}
        if path == "customers":
            return {"customers": [] if off else [
                {"id": 3, "email": "ps@cli.com", "firstname": "Ps", "lastname": "Cli"}]}
        if path == "orders":
            return {"orders": [] if off else [
                {"id": self.order_id, "id_customer": 3, "email": "a@b.c",
                 "associations": {"order_rows": [
                     {"product_reference": "ART001", "product_name": "Prod 1", "product_quantity": "2",
                      "unit_price_tax_incl": "9.90", "product_id": 1}]}}]}
        if method == "PUT":
            self.puts.append(path)
            return {}
        return {}


def _conf():
    S.guardar_runtime("PRESTASHOP", "pk_test")
    os.environ["PRESTASHOP_URL"] = "https://tienda.example.com"


def teardown_function(_):
    # Limpia los pedidos online creados por estos tests (evita acumulación que satura el LIMIT
    # global de listar_pedidos_online entre reejecuciones de la suite).
    try:
        from src.db.conexion import obtener_conexion as _oc
        with _oc() as _c, _c.cursor() as _cur:
            _cur.execute("DELETE FROM pedidos_online WHERE plataforma=%s", ("prestashop",))
            _c.commit()
    except Exception:
        pass
    T.reset_transporte()
    S._reset_runtime()
    os.environ.pop("PRESTASHOP_URL", None)


# ── 1 · Registro sin tocar el motor; degradable; aparece en el Centro ─────────
def test_registro_degradable_y_centro():
    a = ic.motor.adaptador("prestashop")
    assert type(a).__name__ == "PrestaShopAdapter" and a.plataforma == "prestashop"
    S._reset_runtime(); os.environ.pop("PRESTASHOP_URL", None)
    assert a.disponible() is False and a.descriptor()["estado"] == "PREPARADO"
    import pytest
    with pytest.raises(NotImplementedError):
        a.conectar({})
    assert a.autenticar(id_empresa="E1")["codigo"] == "MISSING_CREDENTIALS"
    # Aparece automáticamente en el Centro (WEB-16.5 sin cambios).
    from src.services.marketplace.integraciones_comerciales import centro
    assert any(p["clave"] == "prestashop" for p in centro.plataformas_soportadas())


# ── 2 · Autenticación + validación ────────────────────────────────────────────
def test_autenticar_validar():
    _conf()
    T.set_transporte(_FakePresta())
    a = ic.motor.adaptador("prestashop")
    assert a.disponible("E-PS") is True
    assert a.autenticar(id_empresa="E-PS")["ok"] is True
    v = a.validar(id_empresa="E-PS")
    assert v["ok"] and v["estado"] == "VALIDADA" and v["version"] == "8.1.2"
    assert v["comprobaciones"]["ssl"] == "ok" and v["comprobaciones"]["api"] == "ok"


# ── 3 · Importación reutilizando motores ERP ──────────────────────────────────
def test_importaciones_reutilizan_motor():
    _conf()
    ft = _FakePresta()
    T.set_transporte(ft)
    ref = f"PRESTA-{ft.order_id}"
    a = ic.motor.adaptador("prestashop")
    from src.services.tpv import online_orders_service as OS
    p0 = len(OS.listar_pedidos_online() or [])
    assert a.importar_productos(id_empresa="E-PS")["procesados"] == 1
    assert a.importar_clientes(id_empresa="E-PS")["ok"] is True
    assert a.importar_pedidos(id_empresa="E-PS")["creados"] == 1
    peds = OS.listar_pedidos_online(texto=ref) or []
    assert any(str(p.get("referencia_externa")) == ref
               and str(p.get("plataforma")) == "prestashop" for p in peds)
    assert len(OS.listar_pedidos_online() or []) == p0 + 1


# ── 4 · Idempotencia / sin duplicados ─────────────────────────────────────────
def test_idempotencia():
    _conf()
    T.set_transporte(_FakePresta())
    a = ic.motor.adaptador("prestashop")
    from src.services.tpv import online_orders_service as OS
    a.importar_pedidos(id_empresa="E-PS")
    n1 = len(OS.listar_pedidos_online() or [])
    r2 = a.importar_pedidos(id_empresa="E-PS")
    assert r2["duplicados"] >= 1 and r2["creados"] == 0
    assert len(OS.listar_pedidos_online() or []) == n1


# ── 5 · Exportación stock/precios ─────────────────────────────────────────────
def test_exportacion():
    _conf()
    ft = _FakePresta()
    T.set_transporte(ft)
    a = ic.motor.adaptador("prestashop")
    a.exportar_stock(id_empresa="E-PS", articulos=[{"sku": "ART001", "presta_id": 1, "stock_id": 50}])
    a.exportar_precios(id_empresa="E-PS", articulos=[{"presta_id": 1, "precio": 12.5}])
    assert any("products/1" in p or "stock_availables/50" in p for p in ft.puts)


# ── 6 · Sincronización inicial + incremental ──────────────────────────────────
def test_sincronizacion():
    _conf()
    T.set_transporte(_FakePresta())
    a = ic.motor.adaptador("prestashop")
    assert a.sincronizacion_inicial(id_empresa="E-PS")["ok"] is True
    assert a.sincronizacion_incremental(id_empresa="E-PS")["ok"] is True


# ── 7 · Auditoría PRESTA_* + multiempresa; resto de conectores intactos ───────
def test_auditoria_multiempresa():
    from src.services.marketplace.integraciones_comerciales.prestashop import \
        auditoria
    assert auditoria.EVENTOS == ("PRESTA_AUTH", "PRESTA_VALIDATE", "PRESTA_IMPORT", "PRESTA_EXPORT",
                                 "PRESTA_SYNC_START", "PRESTA_SYNC_FINISH", "PRESTA_ERROR")
    _conf()
    T.set_transporte(_FakePresta())
    a = ic.motor.adaptador("prestashop")
    assert a.importar_productos(id_empresa="EMP_A")["ok"] and a.importar_productos(id_empresa="EMP_B")["ok"]
    # WooCommerce/Shopify (WEB-15/16) siguen intactos; Magento aún PREPARADO.
    assert type(ic.motor.adaptador("shopify")).__name__ == "ShopifyAdapter"
    assert type(ic.motor.adaptador("woocommerce")).__name__ == "WooCommerceAdapter"
    assert ic.motor.adaptador("magento").disponible() is False


# ── 8 · Secretos por SecretManager (API Key cifrada) ──────────────────────────
def test_secretos():
    import inspect
    assert "secret_manager" in inspect.getsource(S) and "cifrar" in inspect.getsource(S)
    S.guardar_runtime("R1", "pk_abc")
    assert S.api_key("R1") == "pk_abc"
    assert S._RUNTIME["R1"] != "pk_abc"   # cifrada en memoria, no en claro
