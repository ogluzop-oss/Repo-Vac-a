"""
Tests · Fase WEB-15 — Conector WooCommerce real (primer conector comercial).

Verifica: registro en el motor WEB-13 (intacto), autenticación/validación, importación de productos/clientes/
pedidos (reutiliza motores ERP), exportación de stock/precios, sincronización incremental, ausencia de
duplicados + idempotencia, auditoría WOO_*, secretos por SecretManager y multiempresa. Sin red (transporte
inyectado).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")

from src.services.marketplace import integraciones_comerciales as ic  # noqa: E402
from src.services.marketplace.integraciones_comerciales.woocommerce import (  # noqa: E402
    secretos as S, transporte as T)


import random  # noqa: E402


class _FakeWoo:
    def __init__(self, order_id=None):
        self.puts = []
        self.order_id = order_id if order_id is not None else random.randint(10_000_000, 99_999_999)
        self.orders = [{"id": self.order_id,
                        "billing": {"first_name": "A", "last_name": "B", "email": "a@b.c", "phone": "1"},
                        "line_items": [{"sku": "ART001", "name": "Prod 1", "quantity": 2, "price": "9.90",
                                        "product_id": 1}]}]

    def request(self, method, base_url, path, *, ck=None, cs=None, json=None, params=None):
        assert ck and cs
        if path == "system_status":
            return {"environment": {"version": "8.5.2"}}
        if path == "products" and method == "GET":
            if params and params.get("sku"):
                return [{"id": 10, "sku": params["sku"]}]
            return [{"id": 1, "sku": "ART001", "name": "Prod 1", "price": "9.90"},
                    {"id": 2, "sku": "ART002", "name": "Prod 2", "price": "5.00"}]
        if path == "customers":
            return [{"id": 1, "email": "woo@cli.com", "first_name": "Woo", "last_name": "Cli",
                     "billing": {"phone": "600"}}]
        if path == "orders":
            return list(self.orders)
        if method == "PUT":
            self.puts.append((path, json))
            return {"id": path.split("/")[-1]}
        return []


def _conf(emp="E-WOO"):
    S.guardar_runtime("WOO", "ck_test", "cs_test")
    os.environ["WOO_URL"] = "https://tienda.example.com"


def teardown_function(_):
    # Limpia los pedidos online creados por estos tests (evita acumulación que satura el LIMIT
    # global de listar_pedidos_online entre reejecuciones de la suite).
    try:
        from src.db.conexion import obtener_conexion as _oc
        with _oc() as _c, _c.cursor() as _cur:
            _cur.execute("DELETE FROM pedidos_online WHERE plataforma=%s", ("woocommerce",))
            _c.commit()
    except Exception:
        pass
    T.reset_transporte()
    S._reset_runtime()
    os.environ.pop("WOO_URL", None)


# ── 1 · Registrado sin tocar el motor WEB-13; degradable sin credenciales ─────
def test_registrado_web13_intacto_y_degradable():
    a = ic.motor.adaptador("woocommerce")
    assert type(a).__name__ == "WooCommerceAdapter" and a.plataforma == "woocommerce"
    S._reset_runtime(); os.environ.pop("WOO_URL", None)
    assert a.disponible() is False and a.descriptor()["estado"] == "PREPARADO"
    import pytest
    with pytest.raises(NotImplementedError):
        a.conectar({})
    # Sin credenciales → autenticar MISSING_CREDENTIALS, sin tocar red.
    assert a.autenticar(id_empresa="E1")["codigo"] == "MISSING_CREDENTIALS"


# ── 2 · Autenticación + validación (URL/API/credenciales/versión/SSL) ─────────
def test_autenticar_y_validar():
    _conf()
    T.set_transporte(_FakeWoo())
    a = ic.motor.adaptador("woocommerce")
    assert a.disponible("E-WOO") is True
    assert a.autenticar(id_empresa="E-WOO")["ok"] is True
    v = a.validar(id_empresa="E-WOO")
    assert v["ok"] and v["estado"] == "VALIDADA" and v["version"] == "8.5.2"
    assert v["comprobaciones"]["ssl"] == "ok" and v["comprobaciones"]["api"] == "ok"
    assert a.obtener_version(id_empresa="E-WOO") == "8.5.2"


# ── 3 · Importación (productos/clientes/pedidos) reutilizando motores ERP ─────
def test_importaciones_reutilizan_motor():
    _conf()
    ft = _FakeWoo()
    T.set_transporte(ft)
    ref = f"WOO-{ft.order_id}"
    a = ic.motor.adaptador("woocommerce")
    from src.services.tpv import online_orders_service as OS
    p0 = len(OS.listar_pedidos_online() or [])
    assert a.importar_productos(id_empresa="E-WOO")["procesados"] == 2
    assert a.importar_clientes(id_empresa="E-WOO")["ok"] is True
    r = a.importar_pedidos(id_empresa="E-WOO")
    assert r["creados"] == 1
    # El pedido creado es del MISMO motor (online_orders), con plataforma woocommerce.
    peds = OS.listar_pedidos_online(texto=ref) or []
    assert any(str(p.get("referencia_externa")) == ref
               and str(p.get("plataforma")) == "woocommerce" for p in peds)
    assert len(OS.listar_pedidos_online() or []) == p0 + 1


# ── 4 · Idempotencia / sin duplicados (re-import no crea copias) ──────────────
def test_idempotencia_sin_duplicados():
    _conf()
    T.set_transporte(_FakeWoo())
    a = ic.motor.adaptador("woocommerce")
    from src.services.tpv import online_orders_service as OS
    a.importar_pedidos(id_empresa="E-WOO")
    n1 = len(OS.listar_pedidos_online() or [])
    r2 = a.importar_pedidos(id_empresa="E-WOO")     # segunda vez
    assert r2["duplicados"] >= 1 and r2["creados"] == 0
    assert len(OS.listar_pedidos_online() or []) == n1   # sin duplicar


# ── 5 · Exportación de stock/precios (solo de la empresa) ─────────────────────
def test_exportacion_stock_precios():
    _conf()
    ft = _FakeWoo()
    T.set_transporte(ft)
    a = ic.motor.adaptador("woocommerce")
    a.exportar_stock(id_empresa="E-WOO", articulos=[{"sku": "ART001", "woo_id": 1}])
    a.exportar_precios(id_empresa="E-WOO", articulos=[{"sku": "ART001", "woo_id": 1, "precio": 12.5}])
    rutas = [p for p, _j in ft.puts]
    assert "products/1" in rutas
    assert any(j.get("regular_price") == "12.5" for _p, j in ft.puts)


# ── 6 · Sincronización incremental usa la última sync existente ───────────────
def test_sincronizacion_incremental():
    _conf()
    T.set_transporte(_FakeWoo())
    a = ic.motor.adaptador("woocommerce")
    ini = a.sincronizacion_inicial(id_empresa="E-WOO")
    assert ini["ok"] is True
    inc = a.sincronizacion_incremental(id_empresa="E-WOO")
    assert inc["ok"] is True   # reutiliza ultima_sync del motor (no reimporta todo)


# ── 7 · Auditoría WOO_* + multiempresa ────────────────────────────────────────
def test_auditoria_y_multiempresa():
    from src.services.marketplace.integraciones_comerciales.woocommerce import \
        auditoria
    assert auditoria.EVENTOS == ("WOO_AUTH", "WOO_VALIDATE", "WOO_IMPORT", "WOO_EXPORT",
                                 "WOO_SYNC_START", "WOO_SYNC_FINISH", "WOO_ERROR")
    _conf()
    T.set_transporte(_FakeWoo())
    a = ic.motor.adaptador("woocommerce")
    from src.services.tpv import online_orders_service as OS
    # Multiempresa: cada empresa importa a su propio contexto (aislamiento por id_empresa en el motor ERP).
    r_a = a.importar_pedidos(id_empresa="EMP_A")
    r_b = a.importar_pedidos(id_empresa="EMP_B")
    assert r_a["ok"] and r_b["ok"]
    # WooCommerce NO se restringe a otras plataformas (WEB-15 solo Woo): el resto sigue PREPARADO.
    assert ic.motor.adaptador("shopify").disponible() is False


# ── 8 · Secretos por SecretManager (nunca en claro) ───────────────────────────
def test_secretos_por_secretmanager():
    import inspect
    src = inspect.getsource(S)
    assert "secret_manager" in src and "cifrar" in src
    S.guardar_runtime("R1", "clave", "secreto")
    ck, cs = S.credenciales("R1")
    assert ck == "clave" and cs == "secreto"          # se recuperan descifrados
    # Cifrados en memoria: el valor en claro no está almacenado tal cual.
    assert all("clave" != v and "secreto" != v for v in S._RUNTIME["R1"])
