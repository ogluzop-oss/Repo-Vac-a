"""Política de cancelación de compras (marketplace/subasta).

Cubre: la matriz de decisión (función pura), la cancelación real de un pedido tramitado con registro,
el bloqueo por tipo/estado (bajo pedido en preparación) y el strike system (que pausa la puja). `db`.
"""

import pytest

from src.db import compras as C
from src.db import proveedores as PROV
from src.services.compras import cancelaciones as CANC

pytestmark = pytest.mark.db


def test_politica_matriz():
    # En cola.
    assert CANC.politica("no_perecedero", "en_cola")["puede_cancelar"] is True
    assert CANC.politica("bajo_pedido", "en_cola")["puede_cancelar"] is False
    assert CANC.politica("no_perecedero", "en_cola", origen="subasta")["puede_cancelar"] is False  # vinculante
    # Pendiente (con y sin ventana de gracia / ventana corta).
    assert CANC.politica("no_perecedero", "pendiente", minutos=200)["puede_cancelar"] is True   # gratuita
    assert CANC.politica("perecedero", "pendiente", minutos=200)["puede_cancelar"] is False     # fuera de ventana
    assert CANC.politica("perecedero", "pendiente", minutos=60)["puede_cancelar"] is True       # gracia
    assert CANC.politica("bajo_pedido", "pendiente", minutos=200,
                         fabricacion_iniciada=True)["puede_cancelar"] is False
    # En preparación.
    r = CANC.politica("no_perecedero", "en_preparacion")
    assert r["puede_cancelar"] is True and r["recargo_pct"] == 15.0
    assert CANC.politica("no_perecedero", "en_preparacion", embalado=True)["bloqueado"] is True
    assert CANC.politica("perecedero", "en_preparacion")["bloqueado"] is True


def _limpia(db, emp, vid=None):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM compras_cancelaciones WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE l FROM compras_pedidos_lineas l JOIN compras_pedidos p "
                    "ON p.id_pedido=l.id_pedido WHERE p.id_empresa=%s", (emp,))
        cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_cancelar_gratuita_y_registro(db, fab):
    emp = fab.empresa("EMP canc")
    cod = fab.articulo(id_empresa=emp, stock_total=0)
    fab.al_limpiar(lambda: _limpia(db, emp))
    prov = PROV.crear_proveedor("P", id_empresa=emp)
    pid = C.crear_pedido(id_proveedor=prov, id_empresa=emp,
                         lineas=[{"codigo": cod, "cantidad": 2, "precio_unitario": 1.0}])
    C.enviar_pedido(pid, emp)

    # No perecedero, recién tramitado → gratuita (dentro de la ventana de gracia).
    pol = CANC.evaluar(pid, emp)
    assert pol["puede_cancelar"] is True and pol["recargo_pct"] == 0.0
    res = CANC.cancelar_pedido(pid, id_empresa=emp, usuario="T")
    assert res["ok"] is True
    assert C.obtener_pedido(pid, emp)["estado"] == "CANCELADO"
    assert CANC.strikes(emp) == 1   # queda registrada


def test_strikes_por_cancelaciones(db, fab):
    """El strike system se conserva: tras STRIKE_UMBRAL cancelaciones recientes, la empresa queda marcada.
    (El consumidor 'pausa de puja' vivía en la Lonja, ya retirada.)"""
    emp = fab.empresa("EMP strike")
    fab.al_limpiar(lambda: _limpia(db, emp))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for _ in range(CANC.STRIKE_UMBRAL):
            cur.execute("INSERT INTO compras_cancelaciones (id_empresa, id_pedido, tipo_producto, estado, "
                        "origen, recargo_pct) VALUES (%s,NULL,'no_perecedero','pendiente','compra_directa',0)",
                        (emp,))
        conn.commit()
    assert CANC.bloqueado_por_strikes(emp) is True
