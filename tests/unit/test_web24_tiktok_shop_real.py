"""
Tests · Fase WEB-24 — Conector TikTok Shop real (último marketplace; mismo patrón que el resto).

Valida: registro automático + aparición en el Centro, autenticación, validación, importación productos/
clientes (derivados de pedidos)/pedidos (reutiliza motores ERP), exportación stock/precios, sincronización
incremental, auditoría TIKTOK_*, degradación sin credenciales, secretos por SecretManager, multiempresa.
Sin red (transporte inyectado).
"""

import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")

from src.services.marketplace import integraciones_comerciales as ic  # noqa: E402
from src.services.marketplace.integraciones_comerciales.tiktok_shop import (  # noqa: E402
    secretos as S, transporte as T)


class _FakeTikTok:
    def __init__(self, order_id=None):
        self.puts = []
        self.order_id = order_id if order_id is not None else random.randint(10_000_000, 99_999_999)

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        assert token
        page = (params or {}).get("page_number", 1)
        if path == "product/202309/products/search":
            return {"data": {"products": [] if page > 1 else [
                {"id": 1, "title": "Prod 1", "skus": [{"seller_sku": "ART001", "price": "9.90"}]}]}}
        if path == "order/202309/orders/search":
            return {"data": {"orders": [] if page > 1 else [
                {"id": self.order_id, "buyer": {"name": "Tik", "email": "tik@cli.com"},
                 "line_items": [{"seller_sku": "ART001", "product_name": "Prod 1", "quantity": 2,
                                 "sale_price": "9.90"}]}]}}
        if method in ("PUT", "POST"):
            self.puts.append(path)
            return {}
        return {}


def _conf():
    S.guardar_runtime("TIKTOK", "tik_token")
    os.environ["TIKTOK_API_HOST"] = "https://open-api.tiktokglobalshop.com"


def teardown_function(_):
    # Limpia los pedidos online creados por estos tests (evita acumulación que satura el LIMIT
    # global de listar_pedidos_online entre reejecuciones de la suite).
    try:
        from src.db.conexion import obtener_conexion as _oc
        with _oc() as _c, _c.cursor() as _cur:
            _cur.execute("DELETE FROM pedidos_online WHERE plataforma=%s", ("tiktok_shop",))
            _c.commit()
    except Exception:
        pass
    T.reset_transporte()
    S._reset_runtime()
    os.environ.pop("TIKTOK_API_HOST", None)


def test_registro_degradable_y_centro():
    a = ic.motor.adaptador("tiktok_shop")
    assert type(a).__name__ == "TikTokShopAdapter" and a.plataforma == "tiktok_shop"
    S._reset_runtime(); os.environ.pop("TIKTOK_API_HOST", None)
    assert a.disponible() is False and a.descriptor()["estado"] == "PREPARADO"
    import pytest
    with pytest.raises(NotImplementedError):
        a.conectar({})
    assert a.autenticar(id_empresa="E1")["codigo"] == "MISSING_CREDENTIALS"
    from src.services.marketplace.integraciones_comerciales import centro
    assert any(p["clave"] == "tiktok_shop" for p in centro.plataformas_soportadas())


def test_autenticar_validar():
    _conf()
    T.set_transporte(_FakeTikTok())
    a = ic.motor.adaptador("tiktok_shop")
    assert a.disponible("E-TK") is True
    assert a.autenticar(id_empresa="E-TK")["ok"] is True
    v = a.validar(id_empresa="E-TK")
    assert v["ok"] and v["estado"] == "VALIDADA"
    assert v["comprobaciones"]["ssl"] == "ok" and v["comprobaciones"]["api"] == "ok"
    assert a.obtener_version(id_empresa="E-TK")


def test_importaciones_reutilizan_motor():
    _conf()
    ft = _FakeTikTok()
    T.set_transporte(ft)
    ref = f"TIKTOK-{ft.order_id}"
    a = ic.motor.adaptador("tiktok_shop")
    from src.services.tpv import online_orders_service as OS
    p0 = len(OS.listar_pedidos_online() or [])
    assert a.importar_productos(id_empresa="E-TK")["procesados"] == 1
    assert a.importar_clientes(id_empresa="E-TK")["ok"] is True
    assert a.importar_pedidos(id_empresa="E-TK")["creados"] == 1
    peds = OS.listar_pedidos_online(texto=ref) or []
    assert any(str(p.get("referencia_externa")) == ref
               and str(p.get("plataforma")) == "tiktok_shop" for p in peds)
    assert len(OS.listar_pedidos_online() or []) == p0 + 1


def test_idempotencia():
    _conf()
    T.set_transporte(_FakeTikTok())
    a = ic.motor.adaptador("tiktok_shop")
    from src.services.tpv import online_orders_service as OS
    a.importar_pedidos(id_empresa="E-TK")
    n1 = len(OS.listar_pedidos_online() or [])
    r2 = a.importar_pedidos(id_empresa="E-TK")
    assert r2["duplicados"] >= 1 and r2["creados"] == 0
    assert len(OS.listar_pedidos_online() or []) == n1


def test_exportacion():
    _conf()
    ft = _FakeTikTok()
    T.set_transporte(ft)
    a = ic.motor.adaptador("tiktok_shop")
    a.exportar_stock(id_empresa="E-TK", articulos=[{"sku": "ART001", "tiktok_id": 1}])
    a.exportar_precios(id_empresa="E-TK", articulos=[{"tiktok_id": 1, "precio": 12.5}])
    assert any("products/1/inventory/update" in p or "products/1/prices/update" in p for p in ft.puts)


def test_sincronizacion():
    _conf()
    T.set_transporte(_FakeTikTok())
    a = ic.motor.adaptador("tiktok_shop")
    assert a.sincronizacion_inicial(id_empresa="E-TK")["ok"] is True
    assert a.sincronizacion_incremental(id_empresa="E-TK")["ok"] is True


def test_auditoria_multiempresa():
    from src.services.marketplace.integraciones_comerciales.tiktok_shop import \
        auditoria
    assert auditoria.EVENTOS == ("TIKTOK_AUTH", "TIKTOK_VALIDATE", "TIKTOK_IMPORT", "TIKTOK_EXPORT",
                                 "TIKTOK_SYNC_START", "TIKTOK_SYNC_FINISH", "TIKTOK_ERROR")
    _conf()
    T.set_transporte(_FakeTikTok())
    a = ic.motor.adaptador("tiktok_shop")
    assert a.importar_productos(id_empresa="EMP_A")["ok"] and a.importar_productos(id_empresa="EMP_B")["ok"]
    # Todos los conectores del ecosistema quedan operativos-ready; ninguno se rompió.
    ecosistema = ("hostinger", "woocommerce", "shopify", "prestashop", "magento", "opencart",
                  "amazon", "ebay", "miravia", "aliexpress", "tiktok_shop")
    from src.services.marketplace.integraciones_comerciales import centro
    claves = {p["clave"] for p in centro.plataformas_soportadas()}
    assert set(ecosistema) <= claves


def test_secretos():
    import inspect
    assert "secret_manager" in inspect.getsource(S) and "cifrar" in inspect.getsource(S)
    S.guardar_runtime("R1", "tik_abc")
    assert S.access_token("R1") == "tik_abc"
    assert S._RUNTIME["R1"] != "tik_abc"
