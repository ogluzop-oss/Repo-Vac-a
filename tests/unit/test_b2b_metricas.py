"""Tests · Métricas de visibilidad (vistas/clics) del catálogo B2B (Smart Suppliers · Fase 3)."""
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


def _limpiar(db, id_suministrador, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM b2b_catalogo_eventos WHERE id_empresa=%s", (id_empresa,))
        cur.execute("DELETE FROM b2b_catalogo WHERE id_suministrador=%s", (id_suministrador,))
        cur.execute("DELETE FROM suministradores WHERE id=%s", (id_suministrador,))
        conn.commit()


def test_registrar_evento_es_idempotente_por_dia(db, fab):
    from src.services.compras import b2b_catalogo as CAT
    emp = fab.empresa("B2B3 METRICAS")
    id_sum = _crear_suministrador(db, "Prov Metricas")
    try:
        CAT.crear_articulo(id_sum, "M1", "Botellas de aceite", unidad_medida="unidad", moq=6,
                          precio_unitario=3.0)
        art = CAT.obtener_activo(id_sum, "M1")

        CAT.registrar_evento(art["id"], emp, "vista")
        CAT.registrar_evento(art["id"], emp, "vista")   # mismo artículo/empresa/tipo/día -> no duplica
        CAT.registrar_evento(art["id"], emp, "click")
        CAT.registrar_evento(art["id"], emp, "tipo_invalido")  # se ignora silenciosamente

        met = CAT.metricas_de_suministrador(id_sum)
        fila = next(m for m in met if m["codigo"] == "M1")
        assert fila["vistas"] == 1
        assert fila["clics"] == 1
    finally:
        _limpiar(db, id_sum, emp)


def test_metricas_incluye_articulos_sin_eventos(db):
    from src.services.compras import b2b_catalogo as CAT
    id_sum = _crear_suministrador(db, "Prov Metricas Vacio")
    try:
        CAT.crear_articulo(id_sum, "M2", "Sin visitas", unidad_medida="kg", moq=1, precio_unitario=1.0)
        met = CAT.metricas_de_suministrador(id_sum)
        fila = next(m for m in met if m["codigo"] == "M2")
        assert fila["vistas"] == 0 and fila["clics"] == 0
    finally:
        _limpiar(db, id_sum, "00000000-0000-0000-0000-000000000001")
