"""Tests · Límite de gasto mensual B2B por empresa (Smart Suppliers · Fase 3)."""
import pytest

pytestmark = pytest.mark.db


def _limpiar(db, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM b2b_empresa_config WHERE id_empresa=%s", (id_empresa,))
        conn.commit()


def test_guardar_y_leer_limite(db, fab):
    from src.services.compras import b2b_presupuesto as PRES
    emp = fab.empresa("B2B3 PRESUP LIMITE")
    try:
        assert PRES.obtener_limite(emp) is None
        assert PRES.guardar_limite(emp, 1000) is True
        assert PRES.obtener_limite(emp) == 1000.0
        assert PRES.guardar_limite(emp, -5) is False   # negativo rechazado
        assert PRES.obtener_limite(emp) == 1000.0       # no se tocó el valor anterior
        assert PRES.guardar_limite(emp, "no_es_numero") is False
    finally:
        _limpiar(db, emp)


def test_resumen_presupuesto_sin_limite_no_finge_porcentaje(db, fab):
    from src.services.compras import b2b_presupuesto as PRES
    emp = fab.empresa("B2B3 PRESUP SIN LIMITE")
    try:
        resumen = PRES.resumen_presupuesto(emp, total_carrito=500)
        assert resumen["limite"] is None
        assert resumen["pct"] is None and resumen["excedido"] is False
    finally:
        _limpiar(db, emp)


def test_resumen_presupuesto_excedido(db, fab):
    from src.services.compras import b2b_presupuesto as PRES
    emp = fab.empresa("B2B3 PRESUP EXCEDIDO")
    try:
        PRES.guardar_limite(emp, 1000)
        ok = PRES.resumen_presupuesto(emp, total_carrito=200)
        assert ok["gasto_mes"] == 0.0 and ok["proyectado"] == 200.0 and ok["excedido"] is False

        excedido = PRES.resumen_presupuesto(emp, total_carrito=2000)
        assert excedido["excedido"] is True
        assert excedido["pct"] > 100
    finally:
        _limpiar(db, emp)
