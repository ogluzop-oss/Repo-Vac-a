"""
Tests · Canal Web WEB-02 (orquestador + Hostinger preparado + Integraciones Comerciales + GUI de entrada).
El Canal Web es el orquestador (¿tiene web? → Hostinger / Marketplace); no gestiona plataformas ni Woo/Shopify.
Sin integraciones reales; degradable; multiempresa.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ── Orquestador (elegir es puro; flujo_inicial degrada sin BD) ────────────────
def test_orquestador_elegir_destinos():
    from src.services.comercio_digital.canal_web import orquestador as O
    a = O.elegir("E1", tiene_web_ya=False)
    assert a["escenario"] == O.SIN_WEB and a["destino"] == O.DESTINO_HOSTINGER
    b = O.elegir("E1", tiene_web_ya=True)
    assert b["escenario"] == O.CON_WEB and b["destino"] == O.DESTINO_INTEGRACIONES


def test_orquestador_flujo_inicial_estructura():
    from src.services.comercio_digital.canal_web import orquestador as O
    f = O.flujo_inicial("E-SINWEB")
    assert "pregunta" in f and f["recomendado"] in (O.SIN_WEB, O.CON_WEB)
    assert f["opciones"][O.SIN_WEB]["destino"] == O.DESTINO_HOSTINGER
    assert f["opciones"][O.CON_WEB]["destino"] == O.DESTINO_INTEGRACIONES


# ── Hostinger: proveedor oficial PREPARADO, no operativo ──────────────────────
def test_hostinger_preparado():
    from src.services.comercio_digital.canal_web import proveedores
    from src.services.comercio_digital.canal_web.proveedores.base import \
        EspecificacionWeb
    prov = proveedores.oficial()
    assert prov.clave == "hostinger" and prov.oficial is True
    assert prov.disponible() is False                       # sin integración real → no operativo
    r = prov.iniciar_creacion(EspecificacionWeb("E1", nombre="Mi Tienda"))
    assert r["estado"] == "PREPARADO" and r["ok"] is False  # nunca simula un sitio real
    assert proveedores.PROVEEDOR_OFICIAL == "hostinger"


# ── Integraciones Comerciales: catálogo PREPARADO, propiedad de Marketplace ────
def test_integraciones_comerciales_catalogo():
    from src.services.comercio_digital import integraciones_comerciales as IC
    claves = {p["clave"] for p in IC.listar_plataformas()}
    assert {"woocommerce", "shopify", "prestashop", "amazon", "ebay", "tiktok_shop"} <= claves
    d = IC.descriptor()
    assert d["propietario"] == "marketplace" and d["origen_redireccion"] == "canal_web"
    assert d["estado"] == "PREPARADO"
    # El contrato de conector existe pero no está operativo.
    from src.services.comercio_digital.integraciones_comerciales.base import \
        ConectorComercial
    assert ConectorComercial().disponible() is False


# ── GUI de entrada (offscreen, degradable) ────────────────────────────────────
def test_canal_web_window_offscreen():
    import pytest
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    from src.gui.canal_web_gui import CanalWebWindow
    app = QApplication.instance() or QApplication([])
    llamado = []
    w = CanalWebWindow(id_empresa="E-GUI", on_ir_marketplace=lambda: llamado.append(1))
    assert w is not None
    # "Sí" → ventana de tipo de web (3 columnas); al elegir un tipo redirige a Marketplace (callback).
    # "No" → asistente Hostinger (índice 1).
    w._elegir(tiene_web=True)
    assert w._stack.currentIndex() == 2
    w._elegir_tipo("ecommerce")
    assert llamado == [1]
    w._elegir(tiene_web=False)
    assert w._stack.currentIndex() == 1
    _ = app
