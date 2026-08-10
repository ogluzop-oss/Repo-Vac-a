"""
Tests · Fase WEB-12 — Canal Web (pregunta única) + Marketplace Integraciones Comerciales + Hostinger.

Verifica (arquitectura preparada, sin conexiones reales):
  1. Canal Web muestra solo la pregunta; "Sí" redirige automáticamente a Marketplace (callback); "No" abre
     el asistente Hostinger (flujo simulado de 6 pasos).
  2. Servicio Integraciones: validar/sincronizar SIMULADOS (transiciones de estado existentes, sin HTTP),
     secretos solo por referencia; estados canónicos.
  3. Centro operativo de Integraciones (GUI) lista plataformas y ejecuta el asistente de alta.
  4. Multiempresa (aislamiento por id_empresa). N7: reutiliza el servicio/estados/catálogo existentes.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")


def _app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ── 1 · Canal Web: pregunta única + flujos ────────────────────────────────────
def test_canal_web_flujo_pregunta():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    from src.gui.canal_web_gui import CanalWebWindow
    llamado = []
    w = CanalWebWindow(id_empresa="E-WEB12", on_ir_marketplace=lambda: llamado.append(1))
    # "Sí" → ventana de tipo de web (3 columnas); al elegir un tipo redirige (callback), sin navegar a mano.
    w._elegir(tiene_web=True)
    assert w._stack.currentIndex() == 2
    w._elegir_tipo("marketplace")
    assert llamado == [1]
    # "No" → creación con Hostinger (índice 1): delegación TOTAL (abre Hostinger), sin pasos simulados.
    w._elegir(tiene_web=False)
    assert w._stack.currentIndex() == 1
    assert hasattr(w, "_abrir_hostinger")
    # ✕ desde Hostinger → 3 columnas; desde 3 columnas → pregunta.
    w._cerrar_o_volver()
    assert w._stack.currentIndex() == 2
    w._cerrar_o_volver()
    assert w._stack.currentIndex() == 0


# ── 2 · Servicio: validar/sincronizar simulados + estados + secretos por ref ──
def test_servicio_validar_sincronizar_simulado():
    from src.services.marketplace import integraciones_comerciales as ic
    ic.servicio._reset_para_tests()
    # Alta con REFERENCIA de credenciales (nunca el valor real).
    r = ic.crear_integracion("E1", "woocommerce", url="https://x.com", credenciales_ref="woo_ref")
    assert r["credenciales_ref"] == "woo_ref" and r["estado"] == ic.estados.CONFIGURADA
    v = ic.validar("E1", "woocommerce")
    assert v["ok"] and v["estado"] == ic.estados.VALIDADA and v["simulada"] is True
    s = ic.sincronizar("E1", "woocommerce")
    assert s["ok"] and s["estado"] == ic.estados.SINCRONIZADA and s["simulada"] is True
    assert set(ic.AMBITOS_SYNC) >= {"productos", "clientes", "pedidos", "reservas", "stock", "precios",
                                    "estados", "click_collect"}
    # Sin referencia de credenciales → validación (simulada) marca ERROR (no HTTP).
    ic.crear_integracion("E1", "shopify")
    assert ic.validar("E1", "shopify")["estado"] == ic.estados.ERROR


# ── 3 · Multiempresa: aislamiento estricto ────────────────────────────────────
def test_multiempresa_aislamiento():
    from src.services.marketplace import integraciones_comerciales as ic
    ic.servicio._reset_para_tests()
    ic.crear_integracion("EMP_A", "woocommerce", credenciales_ref="a")
    ic.crear_integracion("EMP_B", "shopify", credenciales_ref="b")
    a = [i["plataforma"] for i in ic.listar("EMP_A")]
    b = [i["plataforma"] for i in ic.listar("EMP_B")]
    assert a == ["woocommerce"] and b == ["shopify"]


# ── 4 · Centro operativo (GUI): lista plataformas y asistente de alta ─────────
def test_integraciones_gui_operativa():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    from src.services.marketplace import integraciones_comerciales as ic
    ic.servicio._reset_para_tests()
    from src.gui.integraciones_comerciales_gui import \
        IntegracionesComercialesWindow
    win = IntegracionesComercialesWindow(id_empresa="E-GUI")
    # WEB-16.5: el panel muestra la UNIÓN catálogo + adaptadores del motor (≥ catálogo; incluye Hostinger).
    assert win.tabla.rowCount() >= len(ic.listar_plataformas())
    # Asistente de alta: seleccionar → credenciales → guardar+validar+sincronizar (simulado).
    win._asistente.iniciar("E-GUI", None, "woocommerce")
    win._asistente._cred.setText("woo_secret_ref")
    win._asistente._avanzar()   # paso 0 → 1 (credenciales)
    win._asistente._avanzar()   # paso 1 → crea+valida+sincroniza
    assert ic.obtener("E-GUI", "woocommerce")["estado"] == ic.estados.SINCRONIZADA


# ── 5 · N7: reutiliza servicio/estados/catálogo, sin motor nuevo ──────────────
def test_n7_sin_duplicacion():
    import inspect

    from src.gui import integraciones_comerciales_gui as gui
    src = inspect.getsource(gui)
    # La GUI no implementa lógica de estados ni HTTP: delega en el servicio (sin clientes HTTP reales).
    assert "integraciones_comerciales" in src
    for cliente_http in ("import requests", "import urllib", "import httpx", "import aiohttp"):
        assert cliente_http not in src
    # Estados canónicos existentes (no se crean otros).
    from src.services.marketplace.integraciones_comerciales import estados as E
    assert E.ESTADOS == ("NO_CONFIGURADA", "CONFIGURADA", "VALIDADA", "SINCRONIZANDO",
                          "SINCRONIZADA", "ERROR", "DESHABILITADA")
