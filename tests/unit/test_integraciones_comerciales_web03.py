"""
Tests · Marketplace › Integraciones Comerciales (Fase WEB-03). Arquitectura PREPARADA (sin conexiones reales):
modelo de estados, contratos con NotImplementedError, registro multi-tenant con auditoría estructural, sin
credenciales reales. Marketplace de plugins intacto (compatibilidad hacia atrás).
"""

import pytest


@pytest.fixture()
def reset_reg():
    from src.services.marketplace.integraciones_comerciales import servicio
    servicio._reset_para_tests()
    yield
    servicio._reset_para_tests()


# ── Estados unificados ────────────────────────────────────────────────────────
def test_estados_modelo():
    from src.services.marketplace.integraciones_comerciales import estados as E
    assert set(E.ESTADOS) == {"NO_CONFIGURADA", "CONFIGURADA", "VALIDADA", "SINCRONIZANDO",
                              "SINCRONIZADA", "ERROR", "DESHABILITADA"}
    assert E.puede_transicionar(E.CONFIGURADA, E.VALIDADA) is True
    assert E.puede_transicionar(E.SINCRONIZADA, E.NO_CONFIGURADA) is False
    assert E.es_valido("ERROR") and not E.es_valido("XXX")


# ── Catálogo reutilizado (N7, sin duplicar) ───────────────────────────────────
def test_catalogo_reutilizado():
    from src.services.marketplace import integraciones_comerciales as IC
    claves = {p["clave"] for p in IC.listar_plataformas()}
    assert {"woocommerce", "shopify", "prestashop", "magento", "opencart",
            "amazon", "ebay", "miravia", "aliexpress", "tiktok_shop"} <= claves


# ── Contratos: NotImplemented (sin conexión real) ─────────────────────────────
def test_conector_preparado_no_implementado():
    from src.services.marketplace import integraciones_comerciales as IC
    c = IC.obtener_conector("woocommerce")
    assert c.disponible() is False and c.plataforma == "woocommerce"
    for llamada in (lambda: c.conectar({}), lambda: c.sincronizar_productos(),
                    lambda: c.sincronizar_pedidos(), lambda: c.sincronizar_clientes(),
                    lambda: c.sincronizar_stock(), lambda: c.sincronizar_precios(),
                    lambda: c.validar_credenciales({})):
        with pytest.raises(NotImplementedError):
            llamada()
    with pytest.raises(ValueError):
        IC.obtener_conector("plataforma_inexistente")


# ── Registro CRUD + estado + auditoría estructural ────────────────────────────
def test_crud_integracion(reset_reg):
    from src.services.marketplace import integraciones_comerciales as IC
    from src.services.marketplace.integraciones_comerciales import estados as E

    # Sin credenciales → NO_CONFIGURADA; con referencia (nombre de secreto) → CONFIGURADA.
    i0 = IC.crear_integracion("EMP-A", "shopify")
    assert i0["estado"] == E.NO_CONFIGURADA and i0["tipo"] == "ecommerce"
    i1 = IC.crear_integracion("EMP-A", "amazon", credenciales_ref="EMP-A/amazon_api")
    assert i1["estado"] == E.CONFIGURADA and i1["credenciales_ref"] == "EMP-A/amazon_api"
    # NUNCA hay un campo con la credencial en claro (solo la referencia).
    assert "api_key" not in i1 and "secret" not in i1

    # Editar / habilitar-deshabilitar.
    IC.editar_integracion("EMP-A", "shopify", credenciales_ref="EMP-A/shopify_tok")
    assert IC.obtener("EMP-A", "shopify")["estado"] == E.CONFIGURADA
    assert IC.deshabilitar("EMP-A", "shopify")["ok"] and IC.obtener("EMP-A", "shopify")["estado"] == E.DESHABILITADA
    assert IC.habilitar("EMP-A", "shopify")["ok"]
    # Eliminar.
    assert IC.eliminar_integracion("EMP-A", "amazon")["ok"] and IC.obtener("EMP-A", "amazon") is None
    with pytest.raises(ValueError):
        IC.crear_integracion("EMP-A", "plataforma_falsa")


# ── Multi-tenant aislado ──────────────────────────────────────────────────────
def test_multitenant_aislado(reset_reg):
    from src.services.marketplace import integraciones_comerciales as IC
    IC.crear_integracion("EMP-A", "woocommerce")
    IC.crear_integracion("EMP-B", "shopify")
    a = {i["plataforma"] for i in IC.listar("EMP-A")}
    b = {i["plataforma"] for i in IC.listar("EMP-B")}
    assert a == {"woocommerce"} and b == {"shopify"}       # A no ve las de B ni viceversa


def test_estado_integraciones_resumen(reset_reg):
    from src.services.marketplace import integraciones_comerciales as IC
    IC.crear_integracion("EMP-R", "amazon", credenciales_ref="EMP-R/amz")
    res = IC.estado_integraciones("EMP-R")
    amz = next(x for x in res["integraciones"] if x["clave"] == "amazon")
    woo = next(x for x in res["integraciones"] if x["clave"] == "woocommerce")
    assert amz["estado"] == "CONFIGURADA" and woo["estado"] == "NO_CONFIGURADA"


# ── Marketplace de plugins intacto (compatibilidad hacia atrás) ───────────────
def test_marketplace_backward_compat():
    from src.services import marketplace
    # Submódulo nuevo accesible + fachada de plugins intacta.
    assert hasattr(marketplace, "integraciones_comerciales")
    assert marketplace.integraciones_comerciales.descriptor()["propietario"] == "marketplace"
    for fn in ("catalogo", "instalar", "desinstalar", "rollback", "politica"):
        assert hasattr(marketplace, fn)                    # plugins siguen exactamente igual
    d = marketplace.integraciones_comerciales.descriptor()
    assert "hostinger" in d["no_responsabilidades"] and "dominios" in d["no_responsabilidades"]
