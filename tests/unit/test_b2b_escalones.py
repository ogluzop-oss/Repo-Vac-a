"""Tests · Precios escalonados por volumen (rappels) del catálogo B2B (Smart Suppliers · Fase 3)."""
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


def _limpiar(db, id_suministrador):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE e FROM b2b_catalogo_escalones e JOIN b2b_catalogo c ON c.id=e.id_articulo "
                    "WHERE c.id_suministrador=%s", (id_suministrador,))
        cur.execute("DELETE FROM b2b_catalogo WHERE id_suministrador=%s", (id_suministrador,))
        cur.execute("DELETE FROM suministradores WHERE id=%s", (id_suministrador,))
        conn.commit()


def test_precio_para_cantidad_sin_y_con_escalones(db):
    from src.services.compras import b2b_catalogo as CAT
    id_sum = _crear_suministrador(db, "Prov Rappel")
    try:
        r = CAT.crear_articulo(id_sum, "ART1", "Cajas de tomate", unidad_medida="caja", moq=10,
                               precio_unitario=5.0)
        assert r["ok"]
        art = CAT.obtener_activo(id_sum, "ART1")
        assert art and art["precio_unitario"] == 5.0
        assert CAT.precio_para_cantidad(art, 10) == 5.0   # sin escalones: precio piso

        g = CAT.guardar_escalones(id_sum, art["id"], [
            {"cantidad_desde": 50, "precio_unitario": 4.5},
            {"cantidad_desde": 100, "precio_unitario": 4.0},
        ])
        assert g["ok"]
        assert CAT.escalones_de(art["id"])[0]["cantidad_desde"] == 50
        assert CAT.precio_para_cantidad(art, 20) == 5.0    # por debajo del primer escalón
        assert CAT.precio_para_cantidad(art, 50) == 4.5    # justo en el escalón
        assert CAT.precio_para_cantidad(art, 75) == 4.5    # entre escalones
        assert CAT.precio_para_cantidad(art, 100) == 4.0   # segundo escalón
        assert CAT.precio_para_cantidad(art, 500) == 4.0   # por encima, se queda en el último
    finally:
        _limpiar(db, id_sum)


def test_guardar_escalones_valida_y_reemplaza(db):
    from src.services.compras import b2b_catalogo as CAT
    id_sum = _crear_suministrador(db, "Prov Rappel Validacion")
    try:
        CAT.crear_articulo(id_sum, "ART2", "Sacos de arroz", unidad_medida="kg", moq=25,
                          precio_unitario=1.0)
        art = CAT.obtener_activo(id_sum, "ART2")

        # cantidad_desde duplicada -> rechazado, no toca nada.
        bad = CAT.guardar_escalones(id_sum, art["id"], [
            {"cantidad_desde": 50, "precio_unitario": 0.9},
            {"cantidad_desde": 50, "precio_unitario": 0.8},
        ])
        assert bad["ok"] is False
        assert CAT.escalones_de(art["id"]) == []

        # No se puede guardar escalones de un artículo de OTRO proveedor.
        otro = CAT.guardar_escalones(id_sum + 999999, art["id"], [{"cantidad_desde": 10,
                                                                    "precio_unitario": 0.9}])
        assert otro["ok"] is False

        ok1 = CAT.guardar_escalones(id_sum, art["id"], [{"cantidad_desde": 50, "precio_unitario": 0.9}])
        assert ok1["ok"] and len(CAT.escalones_de(art["id"])) == 1

        # Guardar de nuevo REEMPLAZA los anteriores (no los acumula).
        ok2 = CAT.guardar_escalones(id_sum, art["id"], [{"cantidad_desde": 100, "precio_unitario": 0.8}])
        assert ok2["ok"]
        restantes = CAT.escalones_de(art["id"])
        assert len(restantes) == 1 and restantes[0]["cantidad_desde"] == 100
    finally:
        _limpiar(db, id_sum)
