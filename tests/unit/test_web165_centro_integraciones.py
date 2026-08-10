"""
Tests · Fase WEB-16.5 — Consolidación del Centro de Integraciones Comerciales (solo UI/agregación).

Verifica: panel único escalable (unión catálogo + adaptadores del motor), aparición automática de adaptadores
nuevos, indicador de salud, estadísticas e historial reutilizando datos existentes, cola de trabajos local
(pendiente→sincronizando→completado/fallido) y reintento. No modifica motor/adaptadores/conectores.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DB_NAME", "smart_manager_test")

from src.services.marketplace import integraciones_comerciales as ic  # noqa: E402
from src.services.marketplace.integraciones_comerciales import (  # noqa: E402
    centro, cola_jobs)


def _app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ── 1 · Panel escalable: unión catálogo + adaptadores (incluye Hostinger) ─────
def test_plataformas_union_escalable():
    plats = centro.plataformas_soportadas()
    claves = {p["clave"] for p in plats}
    assert claves >= {"hostinger", "woocommerce", "shopify"}                 # adaptadores reales
    assert claves >= {p["clave"] for p in ic.listar_plataformas()}           # + catálogo completo
    assert all("icono" in p and "nombre" in p for p in plats)


# ── 2 · Un adaptador nuevo aparece automáticamente (sin tocar la UI) ──────────
def test_adaptador_nuevo_aparece_solo():
    from src.services.marketplace.integraciones_comerciales.motor import \
        adaptadores as ADAP
    antes = {p["clave"] for p in centro.plataformas_soportadas()}
    assert "plataforma_x" not in antes
    ADAP.ADAPTADORES["plataforma_x"] = ADAP.AdaptadorConector          # registro nuevo
    try:
        despues = {p["clave"] for p in centro.plataformas_soportadas()}
        assert "plataforma_x" in despues                              # aparece sin cambiar la UI
    finally:
        ADAP.ADAPTADORES.pop("plataforma_x", None)


# ── 3 · Indicador de salud (⚪/🟡/🟢/🔴) ───────────────────────────────────────
def test_salud():
    assert centro.salud("SINCRONIZADA") == "OK" and centro.SALUD_EMOJI["OK"] == "🟢"
    assert centro.salud("CONFIGURADA") == "WARN" and centro.SALUD_EMOJI["WARN"] == "🟡"
    assert centro.salud("ERROR") == "ERROR" and centro.SALUD_EMOJI["ERROR"] == "🔴"
    assert centro.salud("NO_CONFIGURADA") == "NONE" and centro.SALUD_EMOJI["NONE"] == "⚪"


# ── 4 · Estadísticas + historial reutilizan datos existentes ──────────────────
def test_estadisticas_e_historial():
    e = centro.estadisticas("E1", "woocommerce")
    assert set(e) >= {"pedidos", "productos", "clientes", "reservas", "stock", "sincronizaciones",
                      "errores", "version_api", "ultima_ejecucion"}
    assert isinstance(e["pedidos"], int)
    assert isinstance(centro.historial("woocommerce", 10), list)     # desde auditoría existente
    r = centro.resumen("E1", "woocommerce")
    assert r["salud_emoji"] in ("🟢", "🟡", "🔴", "⚪") and "version" in r


# ── 5 · Cola de trabajos local: ciclo de estados ──────────────────────────────
def test_cola_trabajos():
    cola_jobs._reset()
    cola_jobs.encolar("E1", "woocommerce")
    cola_jobs.encolar("E1", "shopify")
    assert cola_jobs.resumen()["pendientes"] == 2
    cola_jobs.ejecutar_pendientes(lambda job: (job["plataforma"] != "shopify", {"x": 1}))
    s = cola_jobs.resumen()
    assert s["pendientes"] == 0 and s["completados"] == 1 and s["fallidos"] == 1


# ── 6 · GUI: panel profesional + reintento (degradable, sin crash) ────────────
def test_panel_gui_reintento():
    import pytest
    pytest.importorskip("PyQt6")
    _app()
    cola_jobs._reset()
    from src.gui.integraciones_comerciales_gui import \
        IntegracionesComercialesWindow
    w = IntegracionesComercialesWindow(id_empresa="E-165")
    assert w.tabla.rowCount() == len(centro.plataformas_soportadas())        # escalable
    assert w.tabla.columnCount() == 7                                        # incluye "Salud"
    assert "Salud" in [w.tabla.horizontalHeaderItem(i).text() for i in range(7)]
    # Configura+valida WooCommerce (estado simulado) para que la sincronización de cola complete.
    ic.servicio.crear_integracion("E-165", "woocommerce", credenciales_ref="R", url="https://x.com")
    ic.validar("E-165", "woocommerce")
    fila = next(i for i in range(w.tabla.rowCount())
                if w.tabla.item(i, 0).data(256) == "woocommerce")
    w.tabla.setCurrentCell(fila, 0)
    w._sincronizar()
    assert cola_jobs.resumen()["completados"] >= 1                           # trabajo completado
    w._reintentar()
    assert "reintentar" in w._msg.text().lower()
