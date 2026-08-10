"""
Tests · IA predictiva VISIBLE y OPERATIVA (Fase 7).

Verifica (sin mocks del flujo real): (1) riesgo de rotura como función pura con niveles BAJO/MEDIO/ALTO e
"insuficiente" honesto; (2) el hook conversacional de SOMA/Copilot delega en el motor real y NUNCA calcula la
predicción dentro de SOMA (respuesta explicable / "no hay datos suficientes"); (3) retraining controlado que
solo activa un candidato entrenado si procede; (4) la tarjeta reutilizable se instancia con la librería de
componentes existente (offscreen) sin recalcular predicciones.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ── Fase 2 · Riesgo de rotura (función pura, sin BD) ──────────────────────────
def test_riesgo_rotura_niveles():
    from src.services.prediccion import riesgo_rotura as R

    # Sin demanda fiable → INSUFICIENTE (no inventa).
    assert R.evaluar(stock_actual=10, demanda_diaria=0)["nivel"] == "INSUFICIENTE"

    # No cubre el lead time (disponible < demanda·lead) → ALTO.
    alto = R.evaluar(stock_actual=5, demanda_diaria=10, lead_time=7)
    assert alto["nivel"] == "ALTO" and alto["cobertura_dias"] == 0.5

    # Cobertura holgada → BAJO.
    bajo = R.evaluar(stock_actual=1000, demanda_diaria=10, stock_minimo=50, lead_time=7)
    assert bajo["nivel"] == "BAJO"

    # Cobertura ajustada (< 1.5× lead time) → MEDIO.
    medio = R.evaluar(stock_actual=80, demanda_diaria=10, stock_minimo=5, lead_time=7)
    assert medio["nivel"] == "MEDIO"


# ── Fase 9-11 · SOMA/Copilot delega en el motor real (no calcula en SOMA) ─────
def test_copilot_hook_prediccion_sin_datos():
    from src.services.copilot.motor import CopilotService

    svc = CopilotService()
    ctx = {"id_empresa": "IAUI-EMPTY", "rol": "ADMINISTRADOR", "usuario": 1}
    # Pregunta de previsión sin histórico → responde vía consulta.responder (motor real), honesto.
    r = svc._responder_prediccion("¿cuánto venderemos el próximo mes?", ctx)
    assert r is not None and r["intent"] == "prediccion"
    assert "No hay datos" in r["texto"]                     # nunca inventa cifras
    assert r["fuentes"] == ["PredictiveEngine"]


def test_copilot_hook_no_predictivo_devuelve_none():
    from src.services.copilot.motor import CopilotService

    svc = CopilotService()
    ctx = {"id_empresa": "IAUI-EMPTY", "rol": "ADMINISTRADOR", "usuario": 1}
    # Pregunta ajena a previsión → None (sigue el flujo normal del copiloto).
    assert svc._responder_prediccion("¿quién tiene el turno de mañana?", ctx) is None


# ── Fase 12 · Retraining controlado ───────────────────────────────────────────
@pytest.mark.db
def test_retraining_controlado(db):
    from src.services.prediccion import retraining, modelos as M

    with db.obtener_conexion() as c:
        cur = c.cursor(); cur.execute("DELETE FROM prediccion_modelos WHERE id_empresa='IAUI-RT'"); c.commit()

    # No degradado → no reentrena.
    M.registrar("rt-base", id_empresa="IAUI-RT", entidad="ventas", algoritmo="prophet",
                tipo_modelo="ml", n_observaciones=90, metricas={"mae": 80, "wape": 0.2})
    M.activar("rt-base", id_empresa="IAUI-RT")
    r = retraining.retrain("IAUI-RT", wape_reciente=0.21)   # healthy
    assert r["accion"] == "ninguna"

    # Sin métrica reciente → entrena un candidato real (persistido VALIDATED) y evalúa activación.
    r2 = retraining.retrain("IAUI-RT")
    assert r2["ok"] and r2["accion"] == "retrain" and r2["candidato"]


# ── Fase 1 · Tarjeta reutilizable (offscreen, reutiliza EnterpriseCard) ───────
def test_tarjeta_prevision_offscreen():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    from src.gui import prediccion_card

    app = QApplication.instance() or QApplication([])
    resumen = {"titulo": "PREVISIÓN DE DEMANDA", "horizonte_dias": 30, "total_previsto": 1234.5,
               "modelo": "tendencia_lineal", "tipo_modelo": "modelo estadístico", "es_ml": False,
               "confianza": "media", "calidad_datos": "DATA_QUALITY_GOOD", "n_observaciones": 40,
               "fecha_calculo": "2026-06-30"}
    card = prediccion_card.tarjeta_prevision(resumen)
    assert card is not None
    riesgo = prediccion_card.tarjeta_riesgo({"nivel": "ALTO", "cobertura_dias": 0.5,
                                             "demanda_diaria": 10, "recomendacion": "Reponer ya."})
    assert riesgo is not None
    _ = app


def test_reposicion_page_instancia_con_card_offscreen():
    """La pantalla de reposición se instancia con la tarjeta cableada (degradable) sin romper el arranque."""
    pytest.importorskip("PyQt6")
    pytest.importorskip("pandas")
    from PyQt6.QtWidgets import QApplication
    from src.gui.informe_reposicion import InformeReposicionWindow

    app = QApplication.instance() or QApplication([])
    page = InformeReposicionWindow._EstadoReposicionPage()
    assert page is not None          # sin datos suficientes → card None; nunca lanza excepción
    _ = app
