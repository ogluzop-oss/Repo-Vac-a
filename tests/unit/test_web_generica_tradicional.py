"""
Tests · Web tradicional / genérica (2 modos: feed + REST) — implementación REAL sobre Integraciones
Comerciales, degradable y sin costes.

Verifica:
  1. Los conectores web_feed/web_rest se AUTO-REGISTRAN (tipo 'web_tradicional'). web_feed = capacidad LOCAL
     (disponible); web_rest = degradable (sin URL/token → NO disponible, sin red).
  2. MODO A (feed): generación LOCAL real del catálogo en JSON/CSV/XML (fichero escrito).
  3. MODO B (REST): cliente real con TRANSPORTE INYECTADO (sin HTTP real) — validar + sincronización.
  4. Canal Web "Sí" → 3 columnas; asistente prefiltrado por tipo.
  5. N7: registro por punto de extensión (sin tocar el motor), estados canónicos.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")


def _app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _FakeT:
    """Transporte REST falso (no hace HTTP): registra llamadas y devuelve datos canónicos."""

    def __init__(self):
        self.calls = []

    def request(self, method, base_url, path, *, token=None, json=None, params=None):
        self.calls.append((method, path))
        if path == "productos":
            return [{"id": 1, "codigo": "X"}]
        if path == "pedidos":
            return []          # sin pedidos → no crea órdenes (evita escrituras pesadas en el test)
        return {}


# ── 1 · Registro + disponibilidad (feed local / REST degradable) ──────────────
def test_web_generica_registrada():
    from src.services.marketplace import integraciones_comerciales as ic
    from src.services.marketplace.integraciones_comerciales import motor
    claves = {p["clave"]: p["tipo"] for p in ic.listar_plataformas("web_tradicional")}
    assert claves == {"web_feed": "web_tradicional", "web_rest": "web_tradicional"}
    assert {"web_feed", "web_rest"} <= set(motor.ADAPTADORES)
    # web_feed: capacidad LOCAL siempre disponible. web_rest: degradable (sin URL/token).
    assert motor.adaptador("web_feed").disponible() is True
    assert motor.adaptador("web_rest").disponible() is False
    assert motor.adaptador("web_feed").modo == "feed"
    assert motor.adaptador("web_rest").modo == "rest"


# ── 2 · MODO A · feed real (local, sin red) ───────────────────────────────────
def test_modo_a_feed_real(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # el feed se escribe bajo <tmp>/documentos/…
    from src.services.marketplace.integraciones_comerciales.web_generica import \
        feed
    for fmt in ("json", "csv", "xml"):
        r = feed.generar_feed("E-FEED", formato=fmt)
        assert r["ok"] and r["formato"] == fmt
        assert os.path.exists(r["ruta"]) and r["ruta"].endswith("." + fmt)
        assert r["productos"] >= 0
    # Formato no soportado → error controlado.
    assert feed.generar_feed("E-FEED", formato="pdf")["ok"] is False


# ── 3 · MODO B · REST real con transporte inyectado (sin HTTP) ────────────────
def test_modo_b_rest_real_transporte_inyectado():
    from src.services.marketplace import integraciones_comerciales as ic
    from src.services.marketplace.integraciones_comerciales import motor
    from src.services.marketplace.integraciones_comerciales.web_generica import (
        secretos, transporte)
    ic.servicio._reset_para_tests()
    secretos._reset_runtime()
    ic.crear_integracion("E-REST", "web_rest", url="https://mi.web", credenciales_ref="WR1")
    # Sin token → NO disponible (degradable, sin red).
    assert motor.adaptador("web_rest").disponible("E-REST") is False
    secretos.guardar_runtime("WR1", "tok123")           # token cifrado por referencia (SecretManager)
    fake = _FakeT()
    transporte.set_transporte(fake)
    try:
        adap = motor.adaptador("web_rest")
        assert adap.disponible("E-REST") is True
        v = adap.validar(id_empresa="E-REST")
        assert v["ok"] and ("GET", "productos") in fake.calls
        s = adap.sincronizacion_inicial(id_empresa="E-REST")
        assert s["ok"] and ("GET", "pedidos") in fake.calls
    finally:
        transporte.reset_transporte()
        secretos._reset_runtime()


# ── 4 · Canal Web "Sí" → 3 columnas + asistente prefiltrado por tipo ──────────
def test_canal_web_tres_columnas_y_prefiltro():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    from PyQt6.QtWidgets import QPushButton
    from src.gui.canal_web_gui import CanalWebWindow
    w = CanalWebWindow(id_empresa="E-WT")
    w._elegir(tiene_web=True)
    assert w._stack.currentIndex() == 2
    pag = w._stack.widget(2)
    assert len([b for b in pag.findChildren(QPushButton) if b.text() == "Conectar"]) == 3
    from src.gui.integraciones_comerciales_gui import \
        IntegracionesComercialesWindow
    win = IntegracionesComercialesWindow(id_empresa="E-WT", tipo_inicial="web_tradicional")
    items = {win._asistente._cmb.itemData(i) for i in range(win._asistente._cmb.count())}
    assert items == {"web_feed", "web_rest"}
    win2 = IntegracionesComercialesWindow(id_empresa="E-WT", tipo_inicial="ecommerce")
    assert win2._asistente._cmb.count() == 5


# ── 4b · La tabla filtra por tipo y muestra estado vacío para web propia ──────
def test_tabla_filtra_por_tipo_y_estado_vacio():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    from src.services.marketplace import integraciones_comerciales as ic
    ic.servicio._reset_para_tests()
    from src.gui.integraciones_comerciales_gui import \
        IntegracionesComercialesWindow
    # Web propia sin integraciones → tabla vacía (oculta) + mensaje profesional.
    w = IntegracionesComercialesWindow(id_empresa="E-FILT", tipo_inicial="web_tradicional")
    assert w.tabla.rowCount() == 0 and w.tabla.isHidden()
    assert not w._vacio_lbl.isHidden() and "web propias" in w._vacio_lbl.text().lower()
    # Al configurar una web propia (feed) aparece SOLO ella (filtrada por tipo).
    ic.crear_integracion("E-FILT", "web_feed", credenciales_ref="LOCAL_FEED")
    w._refrescar()
    assert w.tabla.rowCount() == 1 and "Web propia" in w.tabla.item(0, 0).text()
    assert w._vacio_lbl.isHidden() and not w.tabla.isHidden()
    # Apertura directa (sin filtro) → catálogo completo, sin estado vacío.
    w2 = IntegracionesComercialesWindow(id_empresa="E-FILT")
    assert w2.tabla.rowCount() >= 12 and w2._vacio_lbl.isHidden()


# ── 5 · N7: registro por extensión, estados canónicos intactos ────────────────
def test_n7_registro_por_extension():
    import inspect

    from src.services.marketplace.integraciones_comerciales import web_generica
    assert "registrar_adaptador" in inspect.getsource(web_generica)
    from src.services.marketplace.integraciones_comerciales import estados as E
    assert E.ESTADOS == ("NO_CONFIGURADA", "CONFIGURADA", "VALIDADA", "SINCRONIZANDO",
                          "SINCRONIZADA", "ERROR", "DESHABILITADA")
