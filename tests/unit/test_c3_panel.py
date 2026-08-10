"""
Tests Etapa C · Fase C3: Panel Ejecutivo + Alertas Inteligentes (Áreas 5 y 6).

Verifica que el panel COMPONE (no calcula de nuevo) KPIs + decisiones/alertas/predicciones del Centro,
que las alertas se priorizan, que respeta RBAC (`inteligencia.ver`), que es solo lectura y reutiliza
BI + Centro (sin motor/tabla nuevos).
"""

import inspect

import pytest

EMP = "T-PAN-A"
GER = {"id": "g", "perfil": "GERENTE"}


@pytest.fixture()
def datos(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM decisiones_ia WHERE id_empresa=%s", (EMP,))
        conn.commit()
    from src.services import inteligencia
    # Sembramos decisiones de distintos tipos/prioridades a través del Centro.
    inteligencia.proponer("compras", "recomendacion", "Reponer A", "bajo", entidad="articulo",
                          entidad_ref="A", prioridad="ALTA", workflow="compras_pedido", id_empresa=EMP)
    inteligencia.proponer("inventario", "anomalia", "Rotura de stock", "5 art bajo umbral",
                          prioridad="ALTA", id_empresa=EMP)
    inteligencia.proponer("tesoreria", "riesgo", "Impago", "3 facturas", prioridad="MEDIA",
                          id_empresa=EMP)
    inteligencia.proponer("prediccion", "prediccion", "Ventas 7d", "subida prevista", prioridad="INFO",
                          confianza=0.8, id_empresa=EMP)
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM decisiones_ia WHERE id_empresa=%s", (EMP,))
        conn.commit()


def test_panel_compone(datos):
    from src.services.inteligencia import panel
    p = panel.panel(EMP, usuario=GER)
    assert p["ok"] and "kpis" in p and "resumen_decisiones" in p
    assert p["totales"]["prioridades_alta"] == 2      # las 2 ALTA
    assert p["totales"]["alertas"] == 2               # anomalia + riesgo
    assert p["totales"]["recomendaciones"] == 1 and p["totales"]["predicciones"] == 1
    assert p["resumen_decisiones"]["total"] == 4


def test_alertas_priorizadas(datos):
    from src.services.inteligencia import panel
    als = panel.alertas(EMP, usuario=GER)
    assert [a["prioridad"] for a in als] == ["ALTA", "MEDIA"]   # ordenadas por prioridad
    assert {a["tipo"] for a in als} == {"anomalia", "riesgo"}
    # Filtro por prioridad.
    assert all(a["prioridad"] == "ALTA" for a in panel.alertas(EMP, usuario=GER, prioridad="ALTA"))


def test_rbac(datos):
    from src.services.inteligencia import panel
    # Usuario sin permiso inteligencia.ver → no autorizado / vacío.
    sin = {"id": "x", "perfil": "SIN_PERMISO"}
    assert panel.panel(EMP, usuario=sin)["ok"] is False
    assert panel.alertas(EMP, usuario=sin) == []


def test_solo_lectura_reutiliza():
    from src.services.inteligencia import panel
    src = inspect.getsource(panel)
    # Compone sobre bi + Centro; no escribe ni crea motor.
    assert "bi.kpis" in src or "from src.services.bi" in src
    assert "inteligencia" in src
    for prohibido in ("INSERT INTO", "UPDATE ", "CREATE TABLE", "DELETE FROM"):
        assert prohibido not in src
    d = panel.descriptor()
    assert d["solo_lectura"] is True and d["modifica_datos"] is False and d["motor_nuevo"] is False
