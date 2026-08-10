"""
Tests · Fase WEB-21 — Conector eBay real (marketplace; mismo patrón que Amazon/ecommerce).

Verifica: registro en el motor WEB-13 (intacto), autenticación/validación, importación productos/clientes
(derivados del buyer)/pedidos (reutiliza motores ERP), exportación stock/precios, sincronización inicial/
incremental, idempotencia/sin duplicados, auditoría EBAY_*, secretos por SecretManager, multiempresa, y
aparición automática en el Centro (WEB-16.5). Sin red (transporte inyectado).
"""

import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")

from src.services.marketplace import integraciones_comerciales as ic  # noqa: E402
from src.services.marketplace.integraciones_comerciales.ebay import (  # noqa: E402
    secretos as S, transporte as T)


class _FakeEbay:
    def __init__(self, order_id=None):
        self.puts = []
        self.order_id = order_id if order_id is not None else f"{random.randint(10_000, 99_999)}-{random.randint(1000, 9999)}"

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        assert token
        off = (params or {}).get("offset", 0)
        if path == "sell/inventory/v1/inventory_item":
            return {"inventoryItems": [] if off else [
                {"sku": "ART001", "product": {"title": "Prod 1"}, "price": {"value": "9.90"}}], "total": 1}
        if path == "sell/fulfillment/v1/order":
            return {"orders": [] if off else [
                {"orderId": self.order_id, "buyer": {"username": "ebayer", "email": "eb@cli.com"},
                 "lineItems": [{"sku": "ART001", "title": "Prod 1", "quantity": 2,
                                "lineItemCost": {"value": "9.90"}}]}], "total": 1}
        if method in ("PUT", "POST"):
            self.puts.append(path)
            return {}
        return {}


def _conf():
    S.guardar_runtime("EBAY", "ebay_token")
    os.environ["EBAY_API_HOST"] = "https://api.ebay.com"


def teardown_function(_):
    # Limpia los pedidos online creados por estos tests (evita acumulación que satura el LIMIT
    # global de listar_pedidos_online entre reejecuciones de la suite).
    try:
        from src.db.conexion import obtener_conexion as _oc
        with _oc() as _c, _c.cursor() as _cur:
            _cur.execute("DELETE FROM pedidos_online WHERE plataforma=%s", ("ebay",))
            _c.commit()
    except Exception:
        pass
    T.reset_transporte()
    S._reset_runtime()
    os.environ.pop("EBAY_API_HOST", None)


def test_registro_degradable_y_centro():
    a = ic.motor.adaptador("ebay")
    assert type(a).__name__ == "EbayAdapter" and a.plataforma == "ebay"
    S._reset_runtime(); os.environ.pop("EBAY_API_HOST", None)
    assert a.disponible() is False and a.descriptor()["estado"] == "PREPARADO"
    import pytest
    with pytest.raises(NotImplementedError):
        a.conectar({})
    assert a.autenticar(id_empresa="E1")["codigo"] == "MISSING_CREDENTIALS"
    from src.services.marketplace.integraciones_comerciales import centro
    assert any(p["clave"] == "ebay" for p in centro.plataformas_soportadas())


def test_autenticar_validar():
    _conf()
    T.set_transporte(_FakeEbay())
    a = ic.motor.adaptador("ebay")
    assert a.disponible("E-EB") is True
    assert a.autenticar(id_empresa="E-EB")["ok"] is True
    v = a.validar(id_empresa="E-EB")
    assert v["ok"] and v["estado"] == "VALIDADA"
    assert v["comprobaciones"]["ssl"] == "ok" and v["comprobaciones"]["api"] == "ok"
    assert a.obtener_version(id_empresa="E-EB")


def test_importaciones_reutilizan_motor():
    _conf()
    ft = _FakeEbay()
    T.set_transporte(ft)
    ref = f"EBAY-{ft.order_id}"
    a = ic.motor.adaptador("ebay")
    from src.services.tpv import online_orders_service as OS
    p0 = len(OS.listar_pedidos_online() or [])
    assert a.importar_productos(id_empresa="E-EB")["procesados"] == 1
    assert a.importar_clientes(id_empresa="E-EB")["ok"] is True
    assert a.importar_pedidos(id_empresa="E-EB")["creados"] == 1
    peds = OS.listar_pedidos_online(texto=ref) or []
    assert any(str(p.get("referencia_externa")) == ref
               and str(p.get("plataforma")) == "ebay" for p in peds)
    assert len(OS.listar_pedidos_online() or []) == p0 + 1


def test_idempotencia():
    _conf()
    T.set_transporte(_FakeEbay())
    a = ic.motor.adaptador("ebay")
    from src.services.tpv import online_orders_service as OS
    a.importar_pedidos(id_empresa="E-EB")
    n1 = len(OS.listar_pedidos_online() or [])
    r2 = a.importar_pedidos(id_empresa="E-EB")
    assert r2["duplicados"] >= 1 and r2["creados"] == 0
    assert len(OS.listar_pedidos_online() or []) == n1


def test_exportacion():
    _conf()
    ft = _FakeEbay()
    T.set_transporte(ft)
    a = ic.motor.adaptador("ebay")
    a.exportar_stock(id_empresa="E-EB", articulos=[{"sku": "ART001"}])
    a.exportar_precios(id_empresa="E-EB", articulos=[{"sku": "ART001", "precio": 12.5}])
    assert any("inventory_item/ART001" in p or "offer/ART001" in p for p in ft.puts)


def test_sincronizacion():
    _conf()
    T.set_transporte(_FakeEbay())
    a = ic.motor.adaptador("ebay")
    assert a.sincronizacion_inicial(id_empresa="E-EB")["ok"] is True
    assert a.sincronizacion_incremental(id_empresa="E-EB")["ok"] is True


def test_auditoria_multiempresa():
    from src.services.marketplace.integraciones_comerciales.ebay import auditoria
    assert auditoria.EVENTOS == ("EBAY_AUTH", "EBAY_VALIDATE", "EBAY_IMPORT", "EBAY_EXPORT",
                                 "EBAY_SYNC_START", "EBAY_SYNC_FINISH", "EBAY_ERROR")
    _conf()
    T.set_transporte(_FakeEbay())
    a = ic.motor.adaptador("ebay")
    assert a.importar_productos(id_empresa="EMP_A")["ok"] and a.importar_productos(id_empresa="EMP_B")["ok"]
    for plat in ("amazon", "shopify", "woocommerce", "prestashop", "magento", "opencart"):
        assert ic.motor.adaptador(plat).plataforma == plat   # conectores previos intactos
    assert ic.motor.adaptador("miravia").disponible() is False   # siguiente marketplace, aún PREPARADO


def test_secretos():
    import inspect
    assert "secret_manager" in inspect.getsource(S) and "cifrar" in inspect.getsource(S)
    S.guardar_runtime("R1", "ebay_abc")
    assert S.access_token("R1") == "ebay_abc"
    assert S._RUNTIME["R1"] != "ebay_abc"
