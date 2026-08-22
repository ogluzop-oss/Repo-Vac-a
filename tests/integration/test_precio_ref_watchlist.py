"""Precio ref. automático/manual + watchlist (migr 0212 + 0209). `db`.

Verifica la resolución del Precio ref. por prioridad (manual → media ponderada 30 días → precio de alta),
el set/reset del valor manual, y el toggle de la watchlist (en_watchlist/añadir/quitar).
"""

import pytest

pytestmark = pytest.mark.db


def test_precio_referencia_prioridad(db, fab):
    from src.db import empresa as EMP
    from src.db import proveedores as PROV
    from src.db import articulos as A
    from src.db import compras as C
    from src.services.compras import precios_dinamicos as PD

    emp = fab.empresa("EMP pref")
    prev = EMP.empresa_actual_id()
    EMP.set_empresa_actual(emp)

    def _cleanup():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE l FROM compras_pedidos_lineas l JOIN compras_pedidos p "
                        "ON p.id_pedido=l.id_pedido WHERE p.id_empresa=%s", (emp,))
            cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM articulos WHERE id_empresa=%s", (emp,))
            conn.commit()
        EMP.set_empresa_actual(prev)
    fab.al_limpiar(_cleanup)

    # 1) Artículo nuevo sin histórico → Precio ref. = precio de alta.
    assert A.crear_articulo("ARTREF", "Aceite ref", precio=8.0, id_empresa=emp)
    assert PD.precio_referencia("ARTREF", id_empresa=emp) == 8.0
    assert PD.es_ref_manual("ARTREF", id_empresa=emp) is False

    # 2) Con histórico reciente → media PONDERADA por cantidad (2×10 + 8×5)/(10+5) = 60/15 = 4.0.
    idp = PROV.crear_proveedor("Prov ref", id_empresa=emp)
    C.crear_pedido(id_proveedor=idp, id_empresa=emp,
                   lineas=[{"codigo": "ARTREF", "cantidad": 10, "precio_unitario": 2.0}])
    C.crear_pedido(id_proveedor=idp, id_empresa=emp,
                   lineas=[{"codigo": "ARTREF", "cantidad": 5, "precio_unitario": 8.0}])
    ref = PD.precio_referencia("ARTREF", id_empresa=emp)
    assert abs(ref - 4.0) < 0.01
    assert abs(PD.media_historica("ARTREF", id_empresa=emp) - 4.0) < 0.01

    # 3) Valor MANUAL → prioritario, no se recalcula.
    assert PD.set_precio_referencia("ARTREF", 12.5, id_empresa=emp)
    assert PD.precio_referencia("ARTREF", id_empresa=emp) == 12.5
    assert PD.es_ref_manual("ARTREF", id_empresa=emp) is True

    # 4) Restablecer → vuelve a la media histórica.
    assert PD.restablecer_precio_referencia("ARTREF", id_empresa=emp)
    assert PD.es_ref_manual("ARTREF", id_empresa=emp) is False
    assert abs(PD.precio_referencia("ARTREF", id_empresa=emp) - 4.0) < 0.01


def test_watchlist_toggle(db, fab):
    from src.db import empresa as EMP
    from src.services.compras import precios_dinamicos as PD

    emp = fab.empresa("EMP wl")
    prev = EMP.empresa_actual_id()
    EMP.set_empresa_actual(emp)

    def _cleanup():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM compras_watchlist WHERE id_empresa=%s", (emp,))
            conn.commit()
        EMP.set_empresa_actual(prev)
    fab.al_limpiar(_cleanup)

    assert PD.en_watchlist("WLART", id_empresa=emp) is False
    assert PD.añadir_watchlist("WLART", id_empresa=emp)
    assert PD.en_watchlist("WLART", id_empresa=emp) is True
    assert PD.quitar_watchlist("WLART", id_empresa=emp)
    assert PD.en_watchlist("WLART", id_empresa=emp) is False
