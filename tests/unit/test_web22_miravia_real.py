"""
Tests · Fase WEB-22 — Conector Miravia real (marketplace; mismo patrón que Amazon/eBay/ecommerce).

Valida: registro automático + aparición en el Centro, autenticación, validación, importación productos/
clientes (derivados de pedidos)/pedidos (reutiliza motores ERP), exportación stock/precios, sincronización
incremental, auditoría MIRAVIA_*, degradación sin credenciales, secretos por SecretManager, multiempresa.
Sin red (transporte inyectado).
"""

import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")

from src.services.marketplace import integraciones_comerciales as ic  # noqa: E402
from src.services.marketplace.integraciones_comerciales.miravia import (  # noqa: E402
    secretos as S, transporte as T)


class _FakeMiravia:
    def __init__(self, order_id=None):
        self.puts = []
        self.order_id = order_id if order_id is not None else random.randint(10_000_000, 99_999_999)

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        assert token
        off = (params or {}).get("offset", 0)
        if path == "products":
            return {"data": {"products": [] if off else [
                {"item_id": 1, "sku": "ART001", "name": "Prod 1", "price": "9.90"}]}}
        if path == "orders":
            return {"data": {"orders": [] if off else [
                {"order_id": self.order_id, "buyer": {"name": "Mrv", "email": "mrv@cli.com"},
                 "items": [{"sku": "ART001", "name": "Prod 1", "quantity": 2, "price": "9.90"}]}]}}
        if method in ("PUT", "POST"):
            self.puts.append(path)
            return {}
        return {}


def _conf():
    S.guardar_runtime("MIRAVIA", "mrv_token")
    os.environ["MIRAVIA_API_HOST"] = "https://api.miravia.es/rest"


def teardown_function(_):
    # Limpia los pedidos online creados por estos tests (evita acumulación que satura el LIMIT
    # global de listar_pedidos_online entre reejecuciones de la suite).
    try:
        from src.db.conexion import obtener_conexion as _oc
        with _oc() as _c, _c.cursor() as _cur:
            _cur.execute("DELETE FROM pedidos_online WHERE plataforma=%s", ("miravia",))
            _c.commit()
    except Exception:
        pass
    T.reset_transporte()
    S._reset_runtime()
    os.environ.pop("MIRAVIA_API_HOST", None)


def test_registro_degradable_y_centro():
    a = ic.motor.adaptador("miravia")
    assert type(a).__name__ == "MiraviaAdapter" and a.plataforma == "miravia"
    S._reset_runtime(); os.environ.pop("MIRAVIA_API_HOST", None)
    assert a.disponible() is False and a.descriptor()["estado"] == "PREPARADO"
    import pytest
    with pytest.raises(NotImplementedError):
        a.conectar({})
    assert a.autenticar(id_empresa="E1")["codigo"] == "MISSING_CREDENTIALS"
    from src.services.marketplace.integraciones_comerciales import centro
    assert any(p["clave"] == "miravia" for p in centro.plataformas_soportadas())


def test_autenticar_validar():
    _conf()
    T.set_transporte(_FakeMiravia())
    a = ic.motor.adaptador("miravia")
    assert a.disponible("E-MV") is True
    assert a.autenticar(id_empresa="E-MV")["ok"] is True
    v = a.validar(id_empresa="E-MV")
    assert v["ok"] and v["estado"] == "VALIDADA"
    assert v["comprobaciones"]["ssl"] == "ok" and v["comprobaciones"]["api"] == "ok"
    assert a.obtener_version(id_empresa="E-MV")


def test_importaciones_reutilizan_motor():
    _conf()
    ft = _FakeMiravia()
    T.set_transporte(ft)
    ref = f"MIRAVIA-{ft.order_id}"
    a = ic.motor.adaptador("miravia")
    from src.services.tpv import online_orders_service as OS
    p0 = len(OS.listar_pedidos_online() or [])
    assert a.importar_productos(id_empresa="E-MV")["procesados"] == 1
    assert a.importar_clientes(id_empresa="E-MV")["ok"] is True
    assert a.importar_pedidos(id_empresa="E-MV")["creados"] == 1
    peds = OS.listar_pedidos_online(texto=ref) or []
    assert any(str(p.get("referencia_externa")) == ref
               and str(p.get("plataforma")) == "miravia" for p in peds)
    assert len(OS.listar_pedidos_online() or []) == p0 + 1


def test_idempotencia():
    _conf()
    T.set_transporte(_FakeMiravia())
    a = ic.motor.adaptador("miravia")
    from src.services.tpv import online_orders_service as OS
    a.importar_pedidos(id_empresa="E-MV")
    n1 = len(OS.listar_pedidos_online() or [])
    r2 = a.importar_pedidos(id_empresa="E-MV")
    assert r2["duplicados"] >= 1 and r2["creados"] == 0
    assert len(OS.listar_pedidos_online() or []) == n1


def test_exportacion():
    _conf()
    ft = _FakeMiravia()
    T.set_transporte(ft)
    a = ic.motor.adaptador("miravia")
    a.exportar_stock(id_empresa="E-MV", articulos=[{"sku": "ART001", "miravia_id": 1}])
    a.exportar_precios(id_empresa="E-MV", articulos=[{"miravia_id": 1, "precio": 12.5}])
    assert any("products/1" in p for p in ft.puts)


def test_sincronizacion():
    _conf()
    T.set_transporte(_FakeMiravia())
    a = ic.motor.adaptador("miravia")
    assert a.sincronizacion_inicial(id_empresa="E-MV")["ok"] is True
    assert a.sincronizacion_incremental(id_empresa="E-MV")["ok"] is True


def test_auditoria_multiempresa():
    from src.services.marketplace.integraciones_comerciales.miravia import \
        auditoria
    assert auditoria.EVENTOS == ("MIRAVIA_AUTH", "MIRAVIA_VALIDATE", "MIRAVIA_IMPORT", "MIRAVIA_EXPORT",
                                 "MIRAVIA_SYNC_START", "MIRAVIA_SYNC_FINISH", "MIRAVIA_ERROR")
    _conf()
    T.set_transporte(_FakeMiravia())
    a = ic.motor.adaptador("miravia")
    assert a.importar_productos(id_empresa="EMP_A")["ok"] and a.importar_productos(id_empresa="EMP_B")["ok"]
    for plat in ("amazon", "ebay", "shopify", "woocommerce", "prestashop", "magento", "opencart"):
        assert ic.motor.adaptador(plat).plataforma == plat   # conectores previos intactos
    assert ic.motor.adaptador("aliexpress").disponible() is False   # siguiente marketplace, aún PREPARADO


def test_secretos():
    import inspect
    assert "secret_manager" in inspect.getsource(S) and "cifrar" in inspect.getsource(S)
    S.guardar_runtime("R1", "mrv_abc")
    assert S.access_token("R1") == "mrv_abc"
    assert S._RUNTIME["R1"] != "mrv_abc"
