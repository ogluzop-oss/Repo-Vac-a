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
        cur.execute("DELETE FROM portal_pedido_estado WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE l FROM compras_pedidos_lineas l JOIN compras_pedidos p "
                    "ON p.id_pedido=l.id_pedido WHERE p.id_empresa=%s", (emp,))
        cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        if vid:
            cur.execute("DELETE FROM lonja_pujas WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM lonja_listados WHERE id_vendedor=%s", (vid,))
            cur.execute("DELETE FROM lonja_vendedores WHERE id=%s", (vid,))
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


def test_bloqueo_bajo_pedido_en_preparacion(db, fab):
    from src.services.compras import portal
    emp = fab.empresa("EMP canc2")
    cod = fab.articulo(id_empresa=emp, stock_total=0)
    fab.al_limpiar(lambda: _limpia(db, emp))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE articulos SET perecibilidad='bajo_pedido' WHERE codigo=%s", (cod,))
        conn.commit()
    prov = PROV.crear_proveedor("P2", id_empresa=emp)
    pid = C.crear_pedido(id_proveedor=prov, id_empresa=emp,
                         lineas=[{"codigo": cod, "cantidad": 1, "precio_unitario": 1.0}])
    C.enviar_pedido(pid, emp)
    portal.actualizar_estado_pedido(pid, "en_reparto", id_empresa=emp)   # → en preparación

    pol = CANC.evaluar(pid, emp)
    assert pol["estado"] == "en_preparacion" and pol["tipo_producto"] == "bajo_pedido"
    assert pol["puede_cancelar"] is False and pol["bloqueado"] is True
    assert CANC.cancelar_pedido(pid, id_empresa=emp)["error"] == "no_permitido"
    assert C.obtener_pedido(pid, emp)["estado"] != "CANCELADO"           # no se canceló


def test_strike_pausa_la_puja(db, fab):
    from src.services import lonja
    emp = fab.empresa("EMP strike")
    ven = lonja.alta_vendedor("V strike", divisa="EUR")
    fab.al_limpiar(lambda: _limpia(db, emp, ven["id"]))
    # Inyecta STRIKE_UMBRAL cancelaciones recientes.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for _ in range(CANC.STRIKE_UMBRAL):
            cur.execute("INSERT INTO compras_cancelaciones (id_empresa, id_pedido, tipo_producto, estado, "
                        "origen, recargo_pct) VALUES (%s,NULL,'no_perecedero','pendiente','compra_directa',0)",
                        (emp,))
        conn.commit()
    assert CANC.bloqueado_por_strikes(emp) is True
    lid = lonja.publicar(ven["id"], "STK-1", 5.0, puja_minima=5.0, cantidad=5)
    assert lonja.pujar(lid, emp, 6.0)["error"] == "bloqueado_por_cancelaciones"
