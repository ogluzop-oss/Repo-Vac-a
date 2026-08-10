"""
Tests · Ciclo de vida de modelos predictivos + integración SOMA (Fase 6).

Verifica (sin mocks del flujo): persistencia/versionado, validación antes de activar, comparación por
métricas reales (MAE), activación solo si mejora, aislamiento multi-tenant, detección de degradación con
evento, integración SOMA (respuesta con modelo real / rechazo por datos insuficientes / honestidad
heurística-vs-ML) y permisos RBAC.
"""

import pytest

pytestmark = pytest.mark.db

EMP = "PM-1"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM prediccion_modelos WHERE id_empresa LIKE 'PM-%%'")
            c.commit()
    _b()
    yield
    _b()


def test_ciclo_vida_y_comparacion(limpia):
    from src.services.prediccion import modelos as M

    M.registrar("m1", id_empresa=EMP, entidad="ventas", algoritmo="tendencia_lineal",
                tipo_modelo="estadistica", n_observaciones=30, metricas={"mae": 120, "rmse": 150, "wape": 0.3})
    r = M.activar("m1", id_empresa=EMP)                       # sin activo → se activa
    assert r["ok"] and r["activado"]
    assert M.obtener_activo(EMP, "ventas")["model_id"] == "m1"

    # Modelo MEJOR (menor MAE) → se activa y depreca al anterior.
    M.registrar("m2", id_empresa=EMP, entidad="ventas", algoritmo="prophet", tipo_modelo="ml",
                n_observaciones=90, metricas={"mae": 82, "rmse": 100, "wape": 0.2})
    r = M.activar("m2", id_empresa=EMP)
    assert r["ok"] and r["activado"] and r["comparacion"]["criterio"] == "menor_mae"
    assert M.obtener_activo(EMP, "ventas")["model_id"] == "m2"
    assert M.obtener("m1")["estado"] == "DEPRECATED"

    # Modelo PEOR → rechazado (no se activa; el activo sigue siendo m2). Nunca activa por defecto.
    M.registrar("m3", id_empresa=EMP, entidad="ventas", algoritmo="tendencia_lineal",
                tipo_modelo="estadistica", n_observaciones=40, metricas={"mae": 200, "rmse": 250, "wape": 0.5})
    r = M.activar("m3", id_empresa=EMP)
    assert r.get("activado") is False
    assert M.obtener_activo(EMP, "ventas")["model_id"] == "m2"


def test_no_activa_sin_validar(limpia):
    from src.services.prediccion import modelos as M
    M.registrar("mt", id_empresa=EMP, entidad="ventas", algoritmo="prophet", tipo_modelo="ml",
                n_observaciones=90, metricas={"mae": 50}, estado="TRAINING")
    r = M.activar("mt", id_empresa=EMP)
    assert r["ok"] is False and "VALIDATED" in r["error"]      # nunca activa un modelo no validado


def test_aislamiento_multitenant(limpia):
    from src.services.prediccion import modelos as M
    M.registrar("ma", id_empresa=EMP, entidad="ventas", algoritmo="prophet", tipo_modelo="ml",
                n_observaciones=90, metricas={"mae": 60})
    r = M.activar("ma", id_empresa="PM-OTRO")                  # modelo de otro tenant
    assert r["ok"] is False and "tenant" in r["error"]


def test_degradacion(limpia):
    from src.services.prediccion import modelos as M
    M.registrar("md", id_empresa=EMP, entidad="ventas", algoritmo="prophet", tipo_modelo="ml",
                n_observaciones=90, metricas={"mae": 80, "rmse": 100, "wape": 0.2})
    M.activar("md", id_empresa=EMP)
    assert M.evaluar_degradacion(EMP, "ventas", 0.21)["estado"] == "MODEL_HEALTHY"
    assert M.evaluar_degradacion(EMP, "ventas", 0.6)["estado"] in ("MODEL_DEGRADED", "MODEL_RETRAIN_REQUIRED")


def test_forecast_ventas_persiste_modelo(limpia):
    from src.services.prediccion import modelos as M, servicio
    servicio().forecast_ventas("PM-PERSIST", horizonte=7)      # sin histórico → heurística, pero SE REGISTRA
    regs = M.listar("PM-PERSIST", entidad="ventas")
    assert len(regs) >= 1 and regs[0]["estado"] == "VALIDATED" and regs[0]["hash_integridad"]


def test_soma_consulta_honesta(limpia):
    from src.services.prediccion import consulta, forecasting
    # Pregunta no predictiva → no aplicable.
    assert consulta.responder("hola, ¿qué tal?", EMP).get("aplicable") is False
    # Pregunta de ventas sin histórico → suficiente=False, NO inventa.
    r = consulta.responder("¿cuánto venderemos el próximo mes?", "PM-EMPTY")
    assert r["aplicable"] and r["suficiente"] is False and "No hay datos" in r["texto"]
    # resumen_ui: contrato para la UI, con honestidad (heurística no es ML).
    res = forecasting.forecast([100 + i for i in range(30)], horizonte=7, emitir=False)
    ui = consulta.resumen_ui(res)
    assert ui["titulo"] == "PREVISIÓN DE DEMANDA" and ui["es_ml"] is False and "estadístico" in ui["tipo_modelo"]


def test_rbac_permisos_prediccion():
    from src.services.seguridad import catalogo
    for p in ("prediccion.ver", "prediccion.entrenar", "prediccion.activar", "prediccion.gestionar"):
        assert p in catalogo.CATALOGO
