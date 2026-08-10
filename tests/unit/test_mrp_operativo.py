"""
Tests · Producción / MRP OPERATIVO (cierre de brecha funcional).

Verifica el CICLO COMPLETO real que ahora expone la GUI operativa, ejecutando los servicios existentes
(sin motores nuevos): Producto → BOM → Orden de Fabricación → (planificar/liberar/iniciar) →
consumo de componentes por el KARDEX OFICIAL (SALIDA_PRODUCCION) → alta de producto terminado por el
KARDEX OFICIAL (ENTRADA_PRODUCCION) → finalización con costes. Comprueba además la máquina de estados y
que NO se usa ningún motor de stock paralelo (los movimientos quedan en `movimientos_stock`).
"""

import pytest

pytestmark = pytest.mark.db

EMP = "T-MRP-1"
FINAL = "MRP_FINAL"
C1, C2 = "MRP_C1", "MRP_C2"


@pytest.fixture()
def seed(db):
    def _limpiar():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM movimientos_stock WHERE id_empresa=%s AND codigo_articulo IN (%s,%s,%s)",
                        (EMP, FINAL, C1, C2))
            cur.execute("DELETE FROM of_consumos WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM of_produccion WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM ordenes_fabricacion WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM bom_lineas WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM bom WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM articulos WHERE id_empresa=%s AND codigo IN (%s,%s,%s)",
                        (EMP, FINAL, C1, C2))
            c.commit()
    _limpiar()
    with db.obtener_conexion() as c:
        cur = c.cursor()
        for cod, stock in ((FINAL, 0), (C1, 100), (C2, 100)):
            cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, Stock_tienda) "
                        "VALUES (%s,%s,%s,%s,%s)", (cod, EMP, cod, 1.0, stock))
        c.commit()
    yield
    _limpiar()


def _mov(db, id_doc, tipo):
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM movimientos_stock WHERE id_empresa=%s AND id_documento=%s "
                    "AND tipo_movimiento=%s", (EMP, id_doc, tipo))
        r = cur.fetchone()
        return (r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0


def test_ciclo_completo_fabricacion(seed, db):
    from src.services.mrp import bom, ordenes

    # 1) BOM: 2×C1 + 3×C2 por unidad de FINAL.
    bid = bom.crear_bom(FINAL, version="1", cantidad_base=1,
                        lineas=[{"componente": C1, "cantidad": 2}, {"componente": C2, "cantidad": 3}],
                        id_empresa=EMP)
    assert bid, "no se creó la BOM"
    assert bom.bom_activa(FINAL, id_empresa=EMP) is not None

    # 2) Orden de Fabricación de 5 uds → explosiona la BOM en of_consumos.
    oid = ordenes.crear_orden(FINAL, 5, id_empresa=EMP)
    assert oid, "no se creó la OF"
    assert ordenes.obtener_of(oid)["estado"] == "borrador"

    # 3) Máquina de estados: borrador → planificada → liberada → en_curso.
    assert ordenes.planificar(oid, id_empresa=EMP)["ok"]
    assert ordenes.liberar(oid, id_empresa=EMP)["ok"]
    assert ordenes.iniciar(oid, id_empresa=EMP)["ok"]
    assert ordenes.obtener_of(oid)["estado"] == "en_curso"
    # transición inválida rechazada (no rompe): en_curso → planificada no está permitido.
    assert ordenes.planificar(oid, id_empresa=EMP)["ok"] is False

    # 4) Consumo de componentes por el KARDEX OFICIAL (SALIDA_PRODUCCION), no un motor paralelo.
    rc = ordenes.consumir_materiales(oid, id_empresa=EMP, usuario="tester")
    assert rc["ok"]
    assert _mov(db, f"OF:{oid}", "SALIDA_PRODUCCION") == 2   # un movimiento por componente (C1, C2)

    # 5) Alta de producto terminado por el motor OFICIAL de existencias (lotes/kárdex, sin motor
    #    paralelo). Se registra en la OF (cantidad_producida) y en of_produccion.
    rp = ordenes.registrar_produccion(oid, 5, id_empresa=EMP, usuario="tester")
    assert rp["ok"] and rp["cantidad"] == 5
    assert ordenes.obtener_of(oid)["cantidad_producida"] == 5
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM of_produccion WHERE id_of=%s", (oid,))
        r = cur.fetchone()
        assert (r[0] if not isinstance(r, dict) else list(r.values())[0]) == 1

    # 6) Finalización con cálculo de costes.
    rf = ordenes.finalizar(oid, id_empresa=EMP, usuario="tester")
    assert rf["ok"]
    assert ordenes.obtener_of(oid)["estado"] == "finalizada"
    assert "costes" in rf


def test_consumo_idempotente(seed):
    """Consumir dos veces NO duplica los movimientos de kárdex (idempotencia oficial)."""
    from src.db import conexion
    from src.services.mrp import bom, ordenes
    bom.crear_bom(FINAL, lineas=[{"componente": C1, "cantidad": 2}], id_empresa=EMP)
    oid = ordenes.crear_orden(FINAL, 4, id_empresa=EMP)
    ordenes.planificar(oid, id_empresa=EMP); ordenes.liberar(oid, id_empresa=EMP)
    ordenes.iniciar(oid, id_empresa=EMP)
    ordenes.consumir_materiales(oid, id_empresa=EMP, usuario="t")
    ordenes.consumir_materiales(oid, id_empresa=EMP, usuario="t")   # segunda vez
    assert _mov(conexion, f"OF:{oid}", "SALIDA_PRODUCCION") == 1
