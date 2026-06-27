"""
Fabricacion — ciclo completo de OF integrado con el KARDEX existente:
crear -> planificar -> liberar -> iniciar -> consumir (FEFO/kardex) -> producir -> finalizar + costes.
Verifica que el stock se mueve por el kardex real (no sistema paralelo) y las transiciones de estado.
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID

E = EMPRESA_DEFAULT_ID


@pytest.fixture
def escenario(db):
    P = f"PF_{uuid.uuid4().hex[:5]}"
    A = f"CA_{uuid.uuid4().hex[:5]}"
    B = f"CB_{uuid.uuid4().hex[:5]}"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for c in (P, A, B):
            cur.execute("INSERT IGNORE INTO articulos (codigo, nombre, id_empresa) VALUES (%s,%s,%s)", (c, c, E))
        conn.commit()
    from src.db import lotes
    from src.services.mrp import bom
    lotes.registrar_entrada(A, "L"+A, 100, id_empresa=E)
    lotes.registrar_entrada(B, "L"+B, 100, id_empresa=E)
    bom.crear_bom(P, lineas=[{"componente": A, "cantidad": 2}, {"componente": B, "cantidad": 1}], id_empresa=E)
    yield {"P": P, "A": A, "B": B}
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM of_consumos WHERE id_empresa=%s", (E,))
        cur.execute("DELETE FROM of_produccion WHERE id_empresa=%s", (E,))
        cur.execute("DELETE FROM costes_of WHERE id_empresa=%s", (E,))
        cur.execute("DELETE FROM ordenes_fabricacion WHERE id_empresa=%s", (E,))
        cur.execute("DELETE FROM bom_lineas WHERE id_empresa=%s", (E,))
        cur.execute("DELETE FROM bom WHERE id_empresa=%s", (E,))
        cur.execute("DELETE FROM lotes WHERE id_empresa=%s AND codigo_articulo IN (%s,%s,%s)",
                    (E, P, A, B))
        cur.execute("DELETE FROM articulos WHERE codigo IN (%s,%s,%s)", (P, A, B))
        conn.commit()


def test_of_ciclo_completo_kardex(db, escenario):
    from src.db import lotes
    from src.services.mrp import ordenes
    P, A, B = escenario["P"], escenario["A"], escenario["B"]
    oid = ordenes.crear_orden(P, 10, id_empresa=E)
    assert oid
    assert ordenes.planificar(oid, id_empresa=E)["ok"]
    assert ordenes.liberar(oid, id_empresa=E)["ok"]
    assert ordenes.iniciar(oid, id_empresa=E)["ok"]
    # Consumo via kardex/FEFO
    cons = ordenes.consumir_materiales(oid, id_empresa=E)
    assert cons["ok"] and not cons["faltantes"]
    assert lotes.stock_total_en_lotes(A, id_empresa=E) == 80    # 100 - 2*10
    assert lotes.stock_total_en_lotes(B, id_empresa=E) == 90    # 100 - 1*10
    # Produccion -> alta de producto terminado en kardex
    prod = ordenes.registrar_produccion(oid, 10, id_empresa=E)
    assert prod["ok"]
    assert lotes.stock_total_en_lotes(P, id_empresa=E) == 10
    fin = ordenes.finalizar(oid, id_empresa=E)
    assert fin["ok"] and fin["estado"] == "finalizada"


def test_consumo_idempotente(db, escenario):
    from src.db import lotes
    from src.services.mrp import ordenes
    P, A = escenario["P"], escenario["A"]
    oid = ordenes.crear_orden(P, 5, id_empresa=E)
    ordenes.planificar(oid, id_empresa=E); ordenes.liberar(oid, id_empresa=E); ordenes.iniciar(oid, id_empresa=E)
    ordenes.consumir_materiales(oid, id_empresa=E)
    stock1 = lotes.stock_total_en_lotes(A, id_empresa=E)
    ordenes.consumir_materiales(oid, id_empresa=E)              # segunda vez: no vuelve a consumir
    assert lotes.stock_total_en_lotes(A, id_empresa=E) == stock1


def test_transiciones_invalidas(db, escenario):
    from src.services.mrp import ordenes
    oid = ordenes.crear_orden(escenario["P"], 1, id_empresa=E)
    # No se puede finalizar desde borrador
    assert ordenes.finalizar(oid, id_empresa=E)["ok"] is False
    with pytest.raises(ValueError):
        ordenes.cambiar_estado(oid, "estado_inventado", id_empresa=E)
    # Cancelar desde borrador si es valido
    assert ordenes.cancelar(oid, id_empresa=E)["ok"]


def test_kardex_tipos_produccion():
    """Los tipos de produccion estan registrados en el kardex (integracion, no sistema paralelo)."""
    from src.db import kardex, lotes
    assert "ENTRADA_PRODUCCION" in kardex.TIPOS and "SALIDA_PRODUCCION" in kardex.TIPOS
    assert "SALIDA_PRODUCCION" in lotes.TIPOS_SALIDA
