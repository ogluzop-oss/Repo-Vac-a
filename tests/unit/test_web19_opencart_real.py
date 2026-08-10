"""
Tests · Fase WEB-19 — Conector OpenCart real (mismo patrón que WooCommerce/Shopify/PrestaShop/Magento).

Verifica: registro en el motor WEB-13 (intacto), autenticación/validación, importación productos/clientes/
pedidos (reutiliza motores ERP), exportación stock/precios, sincronización inicial/incremental, idempotencia/
sin duplicados, auditoría OPENCART_*, secretos por SecretManager, multiempresa, y aparición automática en el
Centro (WEB-16.5 sin cambios). Sin red (transporte inyectado).
"""

import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")

from src.services.marketplace import integraciones_comerciales as ic  # noqa: E402
from src.services.marketplace.integraciones_comerciales.opencart import (  # noqa: E402
    secretos as S, transporte as T)


class _FakeOpenCart:
    def __init__(self, order_id=None):
        self.puts = []
        self.order_id = order_id if order_id is not None else random.randint(10_000_000, 99_999_999)

    def request(self, method, base_url, path, *, api_key=None, json=None, params=None):
        assert api_key
        page = int((params or {}).get("page", 1)) if params else 1
        if path == "products":
            return {"products": [] if page > 1 else [{"product_id": 1, "sku": "ART001", "model": "M1",
                                                      "name": "Prod 1", "price": "9.90"}]}
        if path == "customers":
            return {"customers": [] if page > 1 else [{"customer_id": 3, "email": "oc@cli.com",
                                                       "firstname": "Oc", "lastname": "Cli"}]}
        if path == "orders":
            return {"orders": [] if page > 1 else [
                {"order_id": self.order_id, "email": "a@b.c", "firstname": "A", "lastname": "B",
                 "products": [{"sku": "ART001", "name": "Prod 1", "quantity": 2, "price": "9.90",
                               "product_id": 1}]}]}
        if method in ("PUT", "POST"):
            self.puts.append(path)
            return {}
        return {}


def _conf():
    S.guardar_runtime("OPENCART", "oc_key")
    os.environ["OPENCART_URL"] = "https://tienda.example.com"


def teardown_function(_):
    # Limpia los pedidos online creados por estos tests (evita acumulación que satura el LIMIT
    # global de listar_pedidos_online entre reejecuciones de la suite).
    try:
        from src.db.conexion import obtener_conexion as _oc
        with _oc() as _c, _c.cursor() as _cur:
            _cur.execute("DELETE FROM pedidos_online WHERE plataforma=%s", ("opencart",))
            _c.commit()
    except Exception:
        pass
    T.reset_transporte()
    S._reset_runtime()
    os.environ.pop("OPENCART_URL", None)


def test_registro_degradable_y_centro():
    a = ic.motor.adaptador("opencart")
    assert type(a).__name__ == "OpenCartAdapter" and a.plataforma == "opencart"
    S._reset_runtime(); os.environ.pop("OPENCART_URL", None)
    assert a.disponible() is False and a.descriptor()["estado"] == "PREPARADO"
    import pytest
    with pytest.raises(NotImplementedError):
        a.conectar({})
    assert a.autenticar(id_empresa="E1")["codigo"] == "MISSING_CREDENTIALS"
    from src.services.marketplace.integraciones_comerciales import centro
    assert any(p["clave"] == "opencart" for p in centro.plataformas_soportadas())


def test_autenticar_validar():
    _conf()
    T.set_transporte(_FakeOpenCart())
    a = ic.motor.adaptador("opencart")
    assert a.disponible("E-OC") is True
    assert a.autenticar(id_empresa="E-OC")["ok"] is True
    v = a.validar(id_empresa="E-OC")
    assert v["ok"] and v["estado"] == "VALIDADA"
    assert v["comprobaciones"]["ssl"] == "ok" and v["comprobaciones"]["api"] == "ok"
    assert a.obtener_version(id_empresa="E-OC")


def test_importaciones_reutilizan_motor():
    _conf()
    ft = _FakeOpenCart()
    T.set_transporte(ft)
    ref = f"OPENCART-{ft.order_id}"
    a = ic.motor.adaptador("opencart")
    from src.services.tpv import online_orders_service as OS
    p0 = len(OS.listar_pedidos_online() or [])
    assert a.importar_productos(id_empresa="E-OC")["procesados"] == 1
    assert a.importar_clientes(id_empresa="E-OC")["ok"] is True
    assert a.importar_pedidos(id_empresa="E-OC")["creados"] == 1
    peds = OS.listar_pedidos_online(texto=ref) or []
    assert any(str(p.get("referencia_externa")) == ref
               and str(p.get("plataforma")) == "opencart" for p in peds)
    assert len(OS.listar_pedidos_online() or []) == p0 + 1


def test_idempotencia():
    _conf()
    T.set_transporte(_FakeOpenCart())
    a = ic.motor.adaptador("opencart")
    from src.services.tpv import online_orders_service as OS
    a.importar_pedidos(id_empresa="E-OC")
    n1 = len(OS.listar_pedidos_online() or [])
    r2 = a.importar_pedidos(id_empresa="E-OC")
    assert r2["duplicados"] >= 1 and r2["creados"] == 0
    assert len(OS.listar_pedidos_online() or []) == n1


def test_exportacion():
    _conf()
    ft = _FakeOpenCart()
    T.set_transporte(ft)
    a = ic.motor.adaptador("opencart")
    a.exportar_stock(id_empresa="E-OC", articulos=[{"sku": "ART001", "oc_id": 1}])
    a.exportar_precios(id_empresa="E-OC", articulos=[{"oc_id": 1, "precio": 12.5}])
    assert any("products/1" in p for p in ft.puts)


def test_sincronizacion():
    _conf()
    T.set_transporte(_FakeOpenCart())
    a = ic.motor.adaptador("opencart")
    assert a.sincronizacion_inicial(id_empresa="E-OC")["ok"] is True
    assert a.sincronizacion_incremental(id_empresa="E-OC")["ok"] is True


def test_auditoria_multiempresa():
    from src.services.marketplace.integraciones_comerciales.opencart import \
        auditoria
    assert auditoria.EVENTOS == ("OPENCART_AUTH", "OPENCART_VALIDATE", "OPENCART_IMPORT", "OPENCART_EXPORT",
                                 "OPENCART_SYNC_START", "OPENCART_SYNC_FINISH", "OPENCART_ERROR")
    _conf()
    T.set_transporte(_FakeOpenCart())
    a = ic.motor.adaptador("opencart")
    assert a.importar_productos(id_empresa="EMP_A")["ok"] and a.importar_productos(id_empresa="EMP_B")["ok"]
    for plat in ("shopify", "woocommerce", "prestashop", "magento"):
        assert ic.motor.adaptador(plat).plataforma == plat   # conectores previos intactos
    assert ic.motor.adaptador("amazon").disponible() is False


def test_secretos():
    import inspect
    assert "secret_manager" in inspect.getsource(S) and "cifrar" in inspect.getsource(S)
    S.guardar_runtime("R1", "oc_abc")
    assert S.api_key("R1") == "oc_abc"
    assert S._RUNTIME["R1"] != "oc_abc"
