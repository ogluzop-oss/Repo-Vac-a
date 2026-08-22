"""Reestructuración Pedidos/Artículos (migr 0211) · capa de datos. `db`.

Verifica: (1) alta de artículo con EAN-13 generado (crear_articulo) + validaciones de unicidad
(existe_codigo/existe_nombre) y disponibilidad inmediata en el buscador; (2) que al crear un pedido se
fija un UUID único y que el PVP dinámico por línea (calculado en la tramitación) se persiste en
compras_pedidos_lineas.pvp_sugerido.
"""

import pytest

pytestmark = pytest.mark.db


def test_alta_articulo_ean(db, fab):
    from src.db import empresa as EMP
    from src.db import articulos as A
    from src.utils import ean

    emp = fab.empresa("EMP ean")
    prev = EMP.empresa_actual_id()
    EMP.set_empresa_actual(emp)

    def _cleanup():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM articulos WHERE id_empresa=%s", (emp,))
            conn.commit()
        EMP.set_empresa_actual(prev)
    fab.al_limpiar(_cleanup)

    codigo = ean.generar(existe_fn=lambda c: A.existe_codigo(c, id_empresa=emp))
    assert ean.es_valido(codigo)
    assert not A.existe_codigo(codigo, id_empresa=emp)
    assert A.crear_articulo(codigo, "Harina de Fuerza EAN", precio=1.25, categoria="Panadería",
                            unidad="kg", id_empresa=emp)
    # Unicidad + disponibilidad inmediata en el buscador de Pedidos.
    assert A.existe_codigo(codigo, id_empresa=emp)
    assert A.existe_nombre("harina de fuerza ean", id_empresa=emp)   # case-insensitive
    assert any(c == codigo for c, _n in A.listar_codigo_nombre(id_empresa=emp))


def test_pedido_uuid_y_pvp(db, fab):
    from src.db import empresa as EMP
    from src.db import proveedores as PROV
    from src.db import compras as C

    emp = fab.empresa("EMP pvp")
    prev = EMP.empresa_actual_id()
    EMP.set_empresa_actual(emp)

    def _cleanup():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE l FROM compras_pedidos_lineas l JOIN compras_pedidos p "
                        "ON p.id_pedido=l.id_pedido WHERE p.id_empresa=%s", (emp,))
            cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
            conn.commit()
        EMP.set_empresa_actual(prev)
    fab.al_limpiar(_cleanup)

    idp = PROV.crear_proveedor("Distribuidor Alim SL", id_empresa=emp)
    # PVP dinámico calculado como en la tramitación: coste 10 × (1 + 30/100) = 13.00.
    lineas = [{"codigo": "ART-PVP", "cantidad": 5, "precio_unitario": 10.0, "pvp_sugerido": 13.0}]
    pid = C.crear_pedido(id_proveedor=idp, lineas=lineas, id_empresa=emp)
    assert pid
    ped = C.obtener_pedido(pid, id_empresa=emp)
    assert ped["uuid"] and len(ped["uuid"]) == 36        # UUID único fijado al crear
    assert ped["numero"] == f"PC{pid:06d}"               # código de referencia
    linea = ped["lineas"][0]
    assert float(linea["pvp_sugerido"]) == 13.0          # PVP dinámico persistido en la línea
