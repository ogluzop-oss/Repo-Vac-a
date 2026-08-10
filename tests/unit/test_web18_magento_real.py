"""
Tests · Fase WEB-18 — Conector Magento real (mismo patrón que WooCommerce/Shopify/PrestaShop).

Verifica: registro en el motor WEB-13 (intacto), autenticación/validación, importación productos/clientes/
pedidos (reutiliza motores ERP), exportación stock/precios, sincronización inicial/incremental, idempotencia/
sin duplicados, auditoría MAGENTO_*, secretos por SecretManager, multiempresa, y aparición automática en el
Centro (WEB-16.5 sin cambios). Sin red (transporte inyectado).
"""

import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")

from src.services.marketplace import integraciones_comerciales as ic  # noqa: E402
from src.services.marketplace.integraciones_comerciales.magento import (  # noqa: E402
    secretos as S, transporte as T)


class _FakeMagento:
    def __init__(self, order_id=None):
        self.puts = []
        self.order_id = order_id if order_id is not None else random.randint(10_000_000, 99_999_999)

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        assert token
        page = int((params or {}).get("searchCriteria[currentPage]", 1)) if params else 1
        if path == "products":
            return {"items": [] if page > 1 else [{"id": 1, "sku": "ART001", "name": "Prod 1",
                                                   "price": 9.90}], "total_count": 1}
        if path == "customers/search":
            return {"items": [] if page > 1 else [{"id": 3, "email": "mg@cli.com", "firstname": "Mg",
                                                   "lastname": "Cli"}], "total_count": 1}
        if path == "orders":
            return {"items": [] if page > 1 else [
                {"entity_id": self.order_id, "customer_email": "a@b.c", "customer_firstname": "A",
                 "customer_lastname": "B", "items": [{"sku": "ART001", "name": "Prod 1",
                                                      "qty_ordered": 2, "price": 9.90, "product_id": 1}]}],
                    "total_count": 1}
        if method in ("PUT", "POST"):
            self.puts.append(path)
            return {}
        return {}


def _conf():
    S.guardar_runtime("MAGENTO", "mag_token")
    os.environ["MAGENTO_URL"] = "https://tienda.example.com"


def teardown_function(_):
    # Limpia los pedidos online creados por estos tests (evita acumulación que satura el LIMIT
    # global de listar_pedidos_online entre reejecuciones de la suite).
    try:
        from src.db.conexion import obtener_conexion as _oc
        with _oc() as _c, _c.cursor() as _cur:
            _cur.execute("DELETE FROM pedidos_online WHERE plataforma=%s", ("magento",))
            _c.commit()
    except Exception:
        pass
    T.reset_transporte()
    S._reset_runtime()
    os.environ.pop("MAGENTO_URL", None)


def test_registro_degradable_y_centro():
    a = ic.motor.adaptador("magento")
    assert type(a).__name__ == "MagentoAdapter" and a.plataforma == "magento"
    S._reset_runtime(); os.environ.pop("MAGENTO_URL", None)
    assert a.disponible() is False and a.descriptor()["estado"] == "PREPARADO"
    import pytest
    with pytest.raises(NotImplementedError):
        a.conectar({})
    assert a.autenticar(id_empresa="E1")["codigo"] == "MISSING_CREDENTIALS"
    from src.services.marketplace.integraciones_comerciales import centro
    assert any(p["clave"] == "magento" for p in centro.plataformas_soportadas())


def test_autenticar_validar():
    _conf()
    T.set_transporte(_FakeMagento())
    a = ic.motor.adaptador("magento")
    assert a.disponible("E-MG") is True
    assert a.autenticar(id_empresa="E-MG")["ok"] is True
    v = a.validar(id_empresa="E-MG")
    assert v["ok"] and v["estado"] == "VALIDADA"
    assert v["comprobaciones"]["ssl"] == "ok" and v["comprobaciones"]["api"] == "ok"
    assert a.obtener_version(id_empresa="E-MG")


def test_importaciones_reutilizan_motor():
    _conf()
    ft = _FakeMagento()
    T.set_transporte(ft)
    ref = f"MAGENTO-{ft.order_id}"
    a = ic.motor.adaptador("magento")
    from src.services.tpv import online_orders_service as OS
    p0 = len(OS.listar_pedidos_online() or [])
    assert a.importar_productos(id_empresa="E-MG")["procesados"] == 1
    assert a.importar_clientes(id_empresa="E-MG")["ok"] is True
    assert a.importar_pedidos(id_empresa="E-MG")["creados"] == 1
    peds = OS.listar_pedidos_online(texto=ref) or []
    assert any(str(p.get("referencia_externa")) == ref
               and str(p.get("plataforma")) == "magento" for p in peds)
    assert len(OS.listar_pedidos_online() or []) == p0 + 1


def test_idempotencia():
    _conf()
    T.set_transporte(_FakeMagento())
    a = ic.motor.adaptador("magento")
    from src.services.tpv import online_orders_service as OS
    a.importar_pedidos(id_empresa="E-MG")
    n1 = len(OS.listar_pedidos_online() or [])
    r2 = a.importar_pedidos(id_empresa="E-MG")
    assert r2["duplicados"] >= 1 and r2["creados"] == 0
    assert len(OS.listar_pedidos_online() or []) == n1


def test_exportacion():
    _conf()
    ft = _FakeMagento()
    T.set_transporte(ft)
    a = ic.motor.adaptador("magento")
    a.exportar_stock(id_empresa="E-MG", articulos=[{"sku": "ART001"}])
    a.exportar_precios(id_empresa="E-MG", articulos=[{"sku": "ART001", "precio": 12.5}])
    assert any("products/ART001" in p for p in ft.puts)


def test_sincronizacion():
    _conf()
    T.set_transporte(_FakeMagento())
    a = ic.motor.adaptador("magento")
    assert a.sincronizacion_inicial(id_empresa="E-MG")["ok"] is True
    assert a.sincronizacion_incremental(id_empresa="E-MG")["ok"] is True


def test_auditoria_multiempresa():
    from src.services.marketplace.integraciones_comerciales.magento import \
        auditoria
    assert auditoria.EVENTOS == ("MAGENTO_AUTH", "MAGENTO_VALIDATE", "MAGENTO_IMPORT", "MAGENTO_EXPORT",
                                 "MAGENTO_SYNC_START", "MAGENTO_SYNC_FINISH", "MAGENTO_ERROR")
    _conf()
    T.set_transporte(_FakeMagento())
    a = ic.motor.adaptador("magento")
    assert a.importar_productos(id_empresa="EMP_A")["ok"] and a.importar_productos(id_empresa="EMP_B")["ok"]
    for plat in ("shopify", "woocommerce", "prestashop"):
        assert ic.motor.adaptador(plat).plataforma == plat   # conectores previos intactos
    assert ic.motor.adaptador("opencart").disponible() is False


def test_secretos():
    import inspect
    assert "secret_manager" in inspect.getsource(S) and "cifrar" in inspect.getsource(S)
    S.guardar_runtime("R1", "mag_abc")
    assert S.access_token("R1") == "mag_abc"
    assert S._RUNTIME["R1"] != "mag_abc"
