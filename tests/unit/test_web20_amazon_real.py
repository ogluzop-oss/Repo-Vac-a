"""
Tests · Fase WEB-20 — Conector Amazon real (primer marketplace; mismo patrón que los ecommerce).

Verifica: registro en el motor WEB-13 (intacto), autenticación/validación, importación productos/clientes/
pedidos (reutiliza motores ERP; clientes derivados del BuyerInfo de los pedidos), exportación stock/precios,
sincronización inicial/incremental, idempotencia/sin duplicados, auditoría AMAZON_*, secretos por SecretManager,
multiempresa, y aparición automática en el Centro (WEB-16.5). Sin red (transporte inyectado).
"""

import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")

from src.services.marketplace import integraciones_comerciales as ic  # noqa: E402
from src.services.marketplace.integraciones_comerciales.amazon import (  # noqa: E402
    secretos as S, transporte as T)


class _FakeAmazon:
    def __init__(self, order_id=None):
        self.puts = []
        self.order_id = order_id if order_id is not None else f"111-{random.randint(1000000, 9999999)}-1"

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        assert token
        has_next = (params or {}).get("NextToken")
        if path == "listings/2021-08-01/items":
            return {"payload": {"items": [] if has_next else [
                {"sku": "ART001", "name": "Prod 1", "price": {"Amount": "9.90"}}]}}
        if path == "orders/v0/orders":
            return {"payload": {"Orders": [] if has_next else [
                {"AmazonOrderId": self.order_id,
                 "BuyerInfo": {"BuyerEmail": "amz@cli.com", "BuyerName": "Amz Cli"}}]}}
        if path.endswith("/orderItems"):
            return {"payload": {"OrderItems": [
                {"SellerSKU": "ART001", "Title": "Prod 1", "QuantityOrdered": 2,
                 "ItemPrice": {"Amount": "9.90"}}]}}
        if method in ("PUT", "POST"):
            self.puts.append(path)
            return {}
        return {}


def _conf():
    S.guardar_runtime("AMAZON", "amz_token")
    os.environ["AMAZON_SPAPI_HOST"] = "https://sellingpartnerapi-eu.amazon.com"


def teardown_function(_):
    # Limpia los pedidos online creados por estos tests (evita acumulación que satura el LIMIT
    # global de listar_pedidos_online entre reejecuciones de la suite).
    try:
        from src.db.conexion import obtener_conexion as _oc
        with _oc() as _c, _c.cursor() as _cur:
            _cur.execute("DELETE FROM pedidos_online WHERE plataforma=%s", ("amazon",))
            _c.commit()
    except Exception:
        pass
    T.reset_transporte()
    S._reset_runtime()
    os.environ.pop("AMAZON_SPAPI_HOST", None)


def test_registro_degradable_y_centro():
    a = ic.motor.adaptador("amazon")
    assert type(a).__name__ == "AmazonAdapter" and a.plataforma == "amazon"
    S._reset_runtime(); os.environ.pop("AMAZON_SPAPI_HOST", None)
    assert a.disponible() is False and a.descriptor()["estado"] == "PREPARADO"
    import pytest
    with pytest.raises(NotImplementedError):
        a.conectar({})
    assert a.autenticar(id_empresa="E1")["codigo"] == "MISSING_CREDENTIALS"
    from src.services.marketplace.integraciones_comerciales import centro
    assert any(p["clave"] == "amazon" for p in centro.plataformas_soportadas())


def test_autenticar_validar():
    _conf()
    T.set_transporte(_FakeAmazon())
    a = ic.motor.adaptador("amazon")
    assert a.disponible("E-AMZ") is True
    assert a.autenticar(id_empresa="E-AMZ")["ok"] is True
    v = a.validar(id_empresa="E-AMZ")
    assert v["ok"] and v["estado"] == "VALIDADA"
    assert v["comprobaciones"]["ssl"] == "ok" and v["comprobaciones"]["api"] == "ok"
    assert a.obtener_version(id_empresa="E-AMZ")


def test_importaciones_reutilizan_motor():
    _conf()
    ft = _FakeAmazon()
    T.set_transporte(ft)
    ref = f"AMAZON-{ft.order_id}"
    a = ic.motor.adaptador("amazon")
    from src.services.tpv import online_orders_service as OS
    p0 = len(OS.listar_pedidos_online() or [])
    assert a.importar_productos(id_empresa="E-AMZ")["procesados"] == 1
    assert a.importar_clientes(id_empresa="E-AMZ")["ok"] is True   # derivados de BuyerInfo
    assert a.importar_pedidos(id_empresa="E-AMZ")["creados"] == 1
    peds = OS.listar_pedidos_online(texto=ref) or []
    assert any(str(p.get("referencia_externa")) == ref
               and str(p.get("plataforma")) == "amazon" for p in peds)
    assert len(OS.listar_pedidos_online() or []) == p0 + 1


def test_idempotencia():
    _conf()
    T.set_transporte(_FakeAmazon())
    a = ic.motor.adaptador("amazon")
    from src.services.tpv import online_orders_service as OS
    a.importar_pedidos(id_empresa="E-AMZ")
    n1 = len(OS.listar_pedidos_online() or [])
    r2 = a.importar_pedidos(id_empresa="E-AMZ")
    assert r2["duplicados"] >= 1 and r2["creados"] == 0
    assert len(OS.listar_pedidos_online() or []) == n1


def test_exportacion():
    _conf()
    ft = _FakeAmazon()
    T.set_transporte(ft)
    a = ic.motor.adaptador("amazon")
    a.exportar_stock(id_empresa="E-AMZ", articulos=[{"sku": "ART001"}])
    a.exportar_precios(id_empresa="E-AMZ", articulos=[{"sku": "ART001", "precio": 12.5}])
    assert any("items/ART001" in p for p in ft.puts)


def test_sincronizacion():
    _conf()
    T.set_transporte(_FakeAmazon())
    a = ic.motor.adaptador("amazon")
    assert a.sincronizacion_inicial(id_empresa="E-AMZ")["ok"] is True
    assert a.sincronizacion_incremental(id_empresa="E-AMZ")["ok"] is True


def test_auditoria_multiempresa():
    from src.services.marketplace.integraciones_comerciales.amazon import \
        auditoria
    assert auditoria.EVENTOS == ("AMAZON_AUTH", "AMAZON_VALIDATE", "AMAZON_IMPORT", "AMAZON_EXPORT",
                                 "AMAZON_SYNC_START", "AMAZON_SYNC_FINISH", "AMAZON_ERROR")
    _conf()
    T.set_transporte(_FakeAmazon())
    a = ic.motor.adaptador("amazon")
    assert a.importar_productos(id_empresa="EMP_A")["ok"] and a.importar_productos(id_empresa="EMP_B")["ok"]
    for plat in ("shopify", "woocommerce", "prestashop", "magento", "opencart"):
        assert ic.motor.adaptador(plat).plataforma == plat   # conectores previos intactos
    assert ic.motor.adaptador("ebay").disponible() is False   # siguiente marketplace, aún PREPARADO


def test_secretos():
    import inspect
    assert "secret_manager" in inspect.getsource(S) and "cifrar" in inspect.getsource(S)
    S.guardar_runtime("R1", "amz_abc")
    assert S.access_token("R1") == "amz_abc"
    assert S._RUNTIME["R1"] != "amz_abc"
