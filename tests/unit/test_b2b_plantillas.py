"""Tests · Plantillas de aprovisionamiento recurrente B2B (Smart Suppliers · Fase 3)."""
import uuid

import pytest

pytestmark = pytest.mark.db


def _crear_suministrador(db, nombre):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO suministradores (razon_social, cif, sector_id, email_login) "
                    "VALUES (%s,%s,%s,%s)",
                    (nombre, "R" + uuid.uuid4().hex[:8], 1, uuid.uuid4().hex[:8] + "@prov.test"))
        id_sum = cur.lastrowid
        conn.commit()
    return id_sum


def _limpiar(db, id_empresa, id_suministrador):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE bl FROM b2b_plantilla_lineas bl JOIN b2b_plantillas b ON b.id=bl.id_plantilla "
                    "WHERE b.id_empresa=%s", (id_empresa,))
        cur.execute("DELETE FROM b2b_plantillas WHERE id_empresa=%s", (id_empresa,))
        cur.execute("DELETE FROM b2b_carrito_lineas WHERE id_suministrador=%s", (id_suministrador,))
        cur.execute("DELETE FROM b2b_catalogo WHERE id_suministrador=%s", (id_suministrador,))
        cur.execute("DELETE FROM suministradores WHERE id=%s", (id_suministrador,))
        conn.commit()


def test_guardar_listar_enviar_eliminar(db, fab):
    from src.services.compras import b2b_carrito as CART, b2b_catalogo as CAT, b2b_plantillas as PLANT
    emp = fab.empresa("B2B3 PLANTILLA")
    id_sum = _crear_suministrador(db, "Prov Plantilla")
    token = "tok-" + uuid.uuid4().hex[:10]
    try:
        CAT.crear_articulo(id_sum, "PL1", "Aceite", unidad_medida="caja", moq=1, precio_unitario=10.0)
        CART.anadir(token, id_suministrador=id_sum, codigo="PL1", nombre="Aceite",
                   unidad_medida="caja", cantidad=3, precio_unitario=10.0)

        vacio = PLANT.guardar_desde_carrito(emp, "  ", token)
        assert vacio["ok"] is False and vacio["error"] == "nombre_obligatorio"

        r = PLANT.guardar_desde_carrito(emp, "Pedido mensual estándar", token)
        assert r["ok"]
        plantillas = PLANT.listar(emp)
        assert len(plantillas) == 1 and plantillas[0]["n_lineas"] == 1

        CART.vaciar(token)
        assert CART.listar(token) == []

        # El precio se re-resuelve contra el catálogo vivo (no se guardó precio en la plantilla).
        env = PLANT.enviar_a_carrito(token, emp, r["id_plantilla"])
        assert env["ok"] and env["anadidas"] == 1 and env["omitidas"] == []
        lineas = CART.listar(token)
        assert len(lineas) == 1 and lineas[0]["codigo"] == "PL1"
        assert float(lineas[0]["precio_unitario"]) == 10.0

        assert PLANT.eliminar(emp, r["id_plantilla"]) is True
        assert PLANT.listar(emp) == []
    finally:
        CART.vaciar(token)
        _limpiar(db, emp, id_sum)


def test_enviar_omite_articulo_desactivado(db, fab):
    from src.services.compras import b2b_carrito as CART, b2b_catalogo as CAT, b2b_plantillas as PLANT
    emp = fab.empresa("B2B3 PLANTILLA DESACT")
    id_sum = _crear_suministrador(db, "Prov Plantilla Desact")
    token = "tok-" + uuid.uuid4().hex[:10]
    try:
        CAT.crear_articulo(id_sum, "PL2", "Vinagre", unidad_medida="caja", moq=1, precio_unitario=5.0)
        CART.anadir(token, id_suministrador=id_sum, codigo="PL2", nombre="Vinagre",
                   unidad_medida="caja", cantidad=2, precio_unitario=5.0)
        r = PLANT.guardar_desde_carrito(emp, "Con artículo que se retira", token)
        CART.vaciar(token)

        CAT.desactivar_articulo(id_sum, "PL2")
        env = PLANT.enviar_a_carrito(token, emp, r["id_plantilla"])
        assert env["ok"] and env["anadidas"] == 0 and env["omitidas"] == ["PL2"]
        assert CART.listar(token) == []
    finally:
        CART.vaciar(token)
        _limpiar(db, emp, id_sum)
