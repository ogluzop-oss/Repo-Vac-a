"""
Tests · Fase WEB-16 — Conector Shopify real (segunda integración comercial, mismo patrón que WooCommerce).

Verifica: registro en el motor WEB-13 (intacto), autenticación/validación, importación productos/clientes/
pedidos (reutiliza motores ERP), exportación stock/precios, sincronización inicial/incremental, idempotencia/
sin duplicados, auditoría SHOPIFY_*, secretos por SecretManager y multiempresa. Sin red (transporte inyectado).
"""

import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")

from src.services.marketplace import integraciones_comerciales as ic  # noqa: E402
from src.services.marketplace.integraciones_comerciales.shopify import (  # noqa: E402
    secretos as S, transporte as T)


class _FakeShop:
    def __init__(self, order_id=None):
        self.puts = []
        self.order_id = order_id if order_id is not None else random.randint(10_000_000, 99_999_999)

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        assert token
        since = (params or {}).get("since_id", 0)
        if path == "shop.json":
            return {"shop": {"name": "Demo", "domain": "demo.myshopify.com"}}
        if path == "products.json":
            return {"products": [] if since else [
                {"id": 100, "title": "SP 1", "variants": [{"id": 1, "sku": "ART001", "price": "9.90"}]}]}
        if path == "customers.json":
            return {"customers": [] if since else [
                {"id": 5, "email": "sh@cli.com", "first_name": "Sh", "last_name": "Cli", "phone": "1"}]}
        if path == "orders.json":
            return {"orders": [] if since else [
                {"id": self.order_id, "customer": {"first_name": "A", "last_name": "B", "email": "a@b.c"},
                 "line_items": [{"sku": "ART001", "title": "SP 1", "quantity": 1, "price": "9.90",
                                 "product_id": 100}]}]}
        if method == "PUT":
            self.puts.append((path, json))
            return {"product": {"id": path}}
        return {}


def _conf():
    S.guardar_runtime("SHOPIFY", "shpat_test")
    os.environ["SHOPIFY_URL"] = "https://demo.myshopify.com"


def teardown_function(_):
    # Limpia los pedidos online creados por estos tests (evita acumulación que satura el LIMIT
    # global de listar_pedidos_online entre reejecuciones de la suite).
    try:
        from src.db.conexion import obtener_conexion as _oc
        with _oc() as _c, _c.cursor() as _cur:
            _cur.execute("DELETE FROM pedidos_online WHERE plataforma=%s", ("shopify",))
            _c.commit()
    except Exception:
        pass
    T.reset_transporte()
    S._reset_runtime()
    os.environ.pop("SHOPIFY_URL", None)


# ── 1 · Registrado sin tocar el motor; degradable sin credenciales ────────────
def test_registrado_web13_intacto_y_degradable():
    a = ic.motor.adaptador("shopify")
    assert type(a).__name__ == "ShopifyAdapter" and a.plataforma == "shopify"
    S._reset_runtime(); os.environ.pop("SHOPIFY_URL", None)
    assert a.disponible() is False and a.descriptor()["estado"] == "PREPARADO"
    import pytest
    with pytest.raises(NotImplementedError):
        a.conectar({})
    assert a.autenticar(id_empresa="E1")["codigo"] == "MISSING_CREDENTIALS"


# ── 2 · Autenticación + validación ────────────────────────────────────────────
def test_autenticar_y_validar():
    _conf()
    T.set_transporte(_FakeShop())
    a = ic.motor.adaptador("shopify")
    assert a.disponible("E-SH") is True
    assert a.autenticar(id_empresa="E-SH")["ok"] is True
    v = a.validar(id_empresa="E-SH")
    assert v["ok"] and v["estado"] == "VALIDADA"
    assert v["comprobaciones"]["ssl"] == "ok" and v["comprobaciones"]["api"] == "ok"
    assert a.obtener_version(id_empresa="E-SH")   # versión de API (constante o cabecera)


# ── 3 · Importación reutilizando motores ERP (mismo pedido online_orders) ─────
def test_importaciones_reutilizan_motor():
    _conf()
    ft = _FakeShop()
    T.set_transporte(ft)
    ref = f"SHOPIFY-{ft.order_id}"
    a = ic.motor.adaptador("shopify")
    from src.services.tpv import online_orders_service as OS
    p0 = len(OS.listar_pedidos_online() or [])
    assert a.importar_productos(id_empresa="E-SH")["procesados"] == 1
    assert a.importar_clientes(id_empresa="E-SH")["ok"] is True
    assert a.importar_pedidos(id_empresa="E-SH")["creados"] == 1
    peds = OS.listar_pedidos_online(texto=ref) or []
    assert any(str(p.get("referencia_externa")) == ref
               and str(p.get("plataforma")) == "shopify" for p in peds)
    assert len(OS.listar_pedidos_online() or []) == p0 + 1


# ── 4 · Idempotencia / sin duplicados ─────────────────────────────────────────
def test_idempotencia():
    _conf()
    T.set_transporte(_FakeShop())
    a = ic.motor.adaptador("shopify")
    from src.services.tpv import online_orders_service as OS
    a.importar_pedidos(id_empresa="E-SH")
    n1 = len(OS.listar_pedidos_online() or [])
    r2 = a.importar_pedidos(id_empresa="E-SH")
    assert r2["duplicados"] >= 1 and r2["creados"] == 0
    assert len(OS.listar_pedidos_online() or []) == n1


# ── 5 · Exportación stock/precios ─────────────────────────────────────────────
def test_exportacion():
    _conf()
    ft = _FakeShop()
    T.set_transporte(ft)
    a = ic.motor.adaptador("shopify")
    a.exportar_stock(id_empresa="E-SH", articulos=[{"sku": "ART001", "shopify_id": 100, "variant_id": 1}])
    a.exportar_precios(id_empresa="E-SH", articulos=[{"shopify_id": 100, "variant_id": 1, "precio": 12.5}])
    assert any(p == "products/100.json" for p, _j in ft.puts)


# ── 6 · Sincronización inicial + incremental ──────────────────────────────────
def test_sincronizacion():
    _conf()
    T.set_transporte(_FakeShop())
    a = ic.motor.adaptador("shopify")
    assert a.sincronizacion_inicial(id_empresa="E-SH")["ok"] is True
    assert a.sincronizacion_incremental(id_empresa="E-SH")["ok"] is True


# ── 7 · Auditoría SHOPIFY_* + multiempresa; resto de plataformas intactas ─────
def test_auditoria_multiempresa():
    from src.services.marketplace.integraciones_comerciales.shopify import \
        auditoria
    assert auditoria.EVENTOS == ("SHOPIFY_AUTH", "SHOPIFY_VALIDATE", "SHOPIFY_IMPORT", "SHOPIFY_EXPORT",
                                 "SHOPIFY_SYNC_START", "SHOPIFY_SYNC_FINISH", "SHOPIFY_ERROR")
    _conf()
    T.set_transporte(_FakeShop())
    a = ic.motor.adaptador("shopify")
    assert a.importar_productos(id_empresa="EMP_A")["ok"] and a.importar_productos(id_empresa="EMP_B")["ok"]
    # WooCommerce (WEB-15) sigue registrado e intacto; PrestaShop aún PREPARADO.
    assert type(ic.motor.adaptador("woocommerce")).__name__ == "WooCommerceAdapter"
    assert ic.motor.adaptador("prestashop").disponible() is False


# ── 8 · Secretos por SecretManager (Access Token cifrado) ─────────────────────
def test_secretos():
    import inspect
    assert "secret_manager" in inspect.getsource(S) and "cifrar" in inspect.getsource(S)
    S.guardar_runtime("R1", "shpat_abc")
    assert S.access_token("R1") == "shpat_abc"
    assert S._RUNTIME["R1"] != "shpat_abc"   # cifrado en memoria, no en claro
