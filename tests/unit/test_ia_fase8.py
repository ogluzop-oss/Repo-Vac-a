"""
Tests · Fase 8 — integración transversal de IA predictiva (SOMA profundo, panel de KPIs, recomendaciones de
reposición, puente SSE→Qt, pantallas). Sin mocks del flujo real; honestidad heurística/estadística/ML;
aislamiento multi-tenant; el motor es único (forecasting) — estos módulos sólo lo consumen.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.db


@pytest.fixture()
def limpia(db):
    """Deja los modelos de los tenants F8-* en estado conocido (evita contaminación entre ejecuciones)."""
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor(); cur.execute("DELETE FROM prediccion_modelos WHERE id_empresa LIKE 'F8-%%'")
            c.commit()
    _b()
    yield
    _b()


# ── Punto 8 · SOMA profundo: enrutado de intents predictivos (sin datos → honesto) ──
def test_consulta_enruta_intents(limpia):
    from src.services.prediccion import consulta

    # Modelos: sin modelos registrados → honesto (se comprueba ANTES de cualquier forecast que persista).
    m = consulta.responder("¿qué modelo se está utilizando?", "F8-NOMODEL")
    assert m["aplicable"] and m.get("intent") == "modelos" and m["suficiente"] is False

    # Riesgo de rotura: tenant vacío → responde con dato real (no hay artículos), no inventa.
    r = consulta.responder("¿qué productos tienen mayor riesgo de rotura?", "F8-EMPTY")
    assert r["aplicable"] and r.get("intent") == "riesgo"

    # Tendencia sin histórico → "no hay datos suficientes".
    t = consulta.responder("¿qué artículos tienen demanda creciente?", "F8-EMPTY")
    assert t["aplicable"] and t.get("intent") == "tendencia" and "datos suficientes" in t["texto"]

    # Pregunta ajena → no aplicable.
    assert consulta.responder("¿qué hora es?", "F8-EMPTY").get("aplicable") is False


# ── Punto 8 · SOMA vía Copilot (reutiliza el hook de Fase 7) ──────────────────
def test_copilot_responde_riesgo():
    from src.services.copilot.motor import CopilotService

    svc = CopilotService()
    ctx = {"id_empresa": "F8-EMPTY", "rol": "ADMINISTRADOR", "usuario": 1}
    r = svc._responder_prediccion("¿qué artículos debería revisar para reponer?", ctx)
    assert r is not None and r["intent"] == "prediccion"
    assert "riesgo de rotura" in r["texto"].lower()


# ── Punto 7 · Panel de KPIs predictivos ───────────────────────────────────────
def test_panel_kpis_estructura():
    from src.services.prediccion import panel

    k = panel.kpis_predictivos("F8-EMPTY")["kpis"]
    assert set(k) >= {"riesgo", "demanda", "modelos", "acciones_recomendadas"}
    assert "explicacion" in k["riesgo"] and "explicacion" in k["demanda"]   # nunca un número sin significado
    assert isinstance(k["acciones_recomendadas"], list) and k["acciones_recomendadas"]
    assert k["demanda"]["tendencia"] == "sin_datos"                         # tenant vacío → honesto


# ── Punto 2/4 · Recomendaciones de reposición (asisten, no auto-pedido) ───────
def test_recomendaciones_reposicion():
    from src.services.prediccion import recomendaciones

    r = recomendaciones.recomendaciones_reposicion("F8-EMPTY")
    assert set(r) >= {"recomendaciones", "n_riesgo", "suficiente"}
    assert isinstance(r["recomendaciones"], list)      # tenant vacío → lista vacía, sin inventar artículos


# ── Punto 10 · Aislamiento multi-tenant (dos tenants vacíos distintos, sin cruce) ──
def test_multitenant_aislado():
    from src.services.prediccion import panel
    a = panel.kpis_predictivos("F8-TA")["kpis"]
    b = panel.kpis_predictivos("F8-TB")["kpis"]
    # Ninguno filtra datos del otro: ambos vacíos e independientes.
    assert a["riesgo"]["articulos_riesgo_alto"] == 0 and b["riesgo"]["articulos_riesgo_alto"] == 0


# ── Punto 7 · Panel GUI offscreen (el EXISTENTE del hub BI, enriquecido con el motor real) ──
def test_panel_prediccion_hub_offscreen():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    from src.gui.paneles.panel_prediccion import PanelPrediccion

    app = QApplication.instance() or QApplication([])
    p = PanelPrediccion(id_empresa="F8-EMPTY")
    p.cargar()                          # ejecuta _refrescar → grid_ia con KPIs del motor real (degradable)
    assert hasattr(p, "grid_ia")
    _ = app


# ── Punto 5 · Puente SSE→Qt (reutiliza RealtimeClient; no simula eventos) ─────
def test_realtime_qt_bridge_offscreen():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    from src.gui.realtime_qt import RealtimePrediccionBridge

    app = QApplication.instance() or QApplication([])
    recibidos = []
    b = RealtimePrediccionBridge("http://localhost:0", lambda: "tok")
    b.prediccion_generada.connect(lambda ev: recibidos.append(ev))
    # Simula la ENTREGA de un evento del transporte (no un evento de negocio inventado): el puente reparte.
    b._on_event({"tipo": "prediccion.generada", "entidad": "ventas"})
    assert recibidos and recibidos[0]["entidad"] == "ventas"
    b.detener()
    _ = app


# ── Punto 1 · Smart Stock instancia con IA cableada (offscreen) ───────────────
def test_smart_stock_page_offscreen():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    from src.gui.mostrar_stock import _StockTiendaPage

    app = QApplication.instance() or QApplication([])
    page = _StockTiendaPage()
    assert page is not None            # la tarjeta IA es degradable; nunca rompe la página
    _ = app
