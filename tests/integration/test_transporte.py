"""
Reparto (R8): flota + rutas de reparto. Entregar una parada DESCUENTA stock por el motor OFICIAL
(kárdex SALIDA_REPARTO), es idempotente y aislado por empresa. Es una FUNCIÓN BASE (no una edición)
gateada por versión: visible en Supermarket/Retail/Pharmacy. Reutiliza los motores de stock generales.
"""

import pytest

pytestmark = pytest.mark.db

from src.services import transporte as T


@pytest.fixture
def emp(fab):
    return fab.empresa("TRANSPORTE R8")


def _articulo(db, emp, cod, stock):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO articulos (codigo,id_empresa,nombre,Stock_tienda,Stock_total) "
                    "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE Stock_tienda=%s,Stock_total=%s",
                    (cod, emp, cod, stock, stock, stock, stock))
        c.commit()


def _stock(db, emp, cod):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT Stock_tienda FROM articulos WHERE codigo=%s AND id_empresa=%s", (cod, emp))
        r = cur.fetchone()
        return int((r[0] if r else 0) or 0)


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    def _borra():
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM transporte_paradas_lineas WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM transporte_paradas WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM transporte_rutas WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM transporte_vehiculos WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM activos WHERE id_empresa=%s AND tipo='vehiculo'", (emp,))
            for cod in ("TRV-A", "TRV-B"):
                cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (cod, emp))
                cur.execute("DELETE FROM movimientos_stock WHERE codigo_articulo=%s", (cod,))
            cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
            c.commit()
    yield
    _borra()


# ── Flota ─────────────────────────────────────────────────────────────────────
def test_crear_y_listar_vehiculo(db, emp):
    vid = T.crear_vehiculo("1234-ABC", descripcion="Furgoneta", capacidad_kg=800, conductor="Luis", id_empresa=emp)
    assert vid
    vehis = T.listar_vehiculos(id_empresa=emp)
    assert any(v["id"] == vid and v["matricula"] == "1234-ABC" for v in vehis)


def test_vehiculo_queda_cableado_como_activo_gmao(db, emp):
    """Reparto ↔ Mantenimiento: dar de alta un vehículo lo registra como ACTIVO GMAO tipo
    'vehiculo' (estado 'operativo' por defecto), visible en el listado de Mantenimiento."""
    from src.services.gmao import activos as A
    vid = T.crear_vehiculo("9999-XYZ", descripcion="Camión", id_empresa=emp)
    vehi = next(v for v in T.listar_vehiculos(id_empresa=emp) if v["id"] == vid)
    assert vehi["id_activo"]
    activo = A.buscar_por_codigo("9999-XYZ", id_empresa=emp)
    assert activo is not None
    assert activo["id"] == vehi["id_activo"]
    assert activo["tipo"] == "vehiculo"
    assert activo["estado"] == "operativo"
    assert any(a["id"] == activo["id"] for a in A.listar(id_empresa=emp))


def test_listar_vehiculos_repara_enlace_gmao_huerfano(db, emp):
    """Un vehículo que por el motivo que sea se quedara SIN activo enlazado (`id_activo` NULL —
    p. ej. creado antes de este cableado, o un fallo puntual de GMAO en su momento) se repara solo
    al listar, sin intervención manual: Reparto y Mantenimiento quedan SIEMPRE cableados."""
    from src.services.gmao import activos as A
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO transporte_vehiculos (id_empresa, matricula, descripcion, id_activo) "
                    "VALUES (%s,%s,%s,NULL)", (emp, "7777-HUE", "Furgón huérfano"))
        c.commit()
    assert A.buscar_por_codigo("7777-HUE", id_empresa=emp) is None   # aún sin activo

    vehis = T.listar_vehiculos(id_empresa=emp)
    vehi = next(v for v in vehis if v["matricula"] == "7777-HUE")
    assert vehi["id_activo"]   # reparado en esta misma lectura

    activo = A.buscar_por_codigo("7777-HUE", id_empresa=emp)
    assert activo is not None and activo["id"] == vehi["id_activo"] and activo["tipo"] == "vehiculo"
    # Persistido de verdad (no solo en memoria): una segunda lectura ve el mismo id_activo.
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT id_activo FROM transporte_vehiculos WHERE matricula=%s AND id_empresa=%s",
                    ("7777-HUE", emp))
        assert cur.fetchone()[0] == vehi["id_activo"]


# ── Rutas + entrega (descuenta stock por el motor oficial) ────────────────────
def test_entregar_parada_descuenta_stock_por_kardex(db, emp):
    _articulo(db, emp, "TRV-A", 10)
    _articulo(db, emp, "TRV-B", 5)
    rid = T.crear_ruta("2031-09-01", conductor="Ana", id_empresa=emp, paradas=[
        {"cliente": "Cliente 1", "direccion": "C/ Uno",
         "lineas": [{"codigo": "TRV-A", "cantidad": 3}, {"codigo": "TRV-B", "cantidad": 2}]},
    ])
    assert rid
    assert T.iniciar_ruta(rid, id_empresa=emp) is True
    ruta = T.obtener_ruta(rid, id_empresa=emp)
    parada = ruta["paradas"][0]

    r = T.entregar_parada(parada["id"], id_empresa=emp, usuario="Ana")
    assert r["ok"] and r["entregadas"] == 2
    assert _stock(db, emp, "TRV-A") == 7      # 10 - 3
    assert _stock(db, emp, "TRV-B") == 3      # 5 - 2
    # kárdex oficial con el tipo SALIDA_REPARTO
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM movimientos_stock WHERE codigo_articulo='TRV-A' "
                    "AND tipo_movimiento='SALIDA_REPARTO'")
        assert (cur.fetchone()[0] or 0) >= 1


def test_entregar_parada_idempotente(db, emp):
    _articulo(db, emp, "TRV-A", 10)
    rid = T.crear_ruta("2031-09-02", id_empresa=emp, paradas=[
        {"cliente": "C", "lineas": [{"codigo": "TRV-A", "cantidad": 4}]}])
    parada = T.obtener_ruta(rid, id_empresa=emp)["paradas"][0]
    T.entregar_parada(parada["id"], id_empresa=emp)
    r2 = T.entregar_parada(parada["id"], id_empresa=emp)   # 2ª vez: no vuelve a descontar
    assert r2.get("ya") is True
    assert _stock(db, emp, "TRV-A") == 6                    # 10 - 4 (una sola vez)


def test_cerrar_ruta(db, emp):
    _articulo(db, emp, "TRV-A", 10)
    rid = T.crear_ruta("2031-09-03", id_empresa=emp, paradas=[
        {"cliente": "C", "lineas": [{"codigo": "TRV-A", "cantidad": 1}]}])
    parada = T.obtener_ruta(rid, id_empresa=emp)["paradas"][0]
    assert T.cerrar_ruta(rid, id_empresa=emp)["ok"] is False    # aún pendiente
    T.entregar_parada(parada["id"], id_empresa=emp)
    assert T.cerrar_ruta(rid, id_empresa=emp)["ok"] is True
    assert T.obtener_ruta(rid, id_empresa=emp)["estado"] == "cerrada"


# ── Segmentación: FUNCIÓN BASE gateada por versión (Reparto no es una edición) ──
def test_reparto_es_funcion_base_gateada_por_version():
    from src.services import verticales as V
    assert "TRANSPORTE" not in V.VERTICALES               # ya NO es una edición
    for e in ("SUPERMARKET", "RETAIL", "PHARMACY", "TEXTIL"):   # comercio con reparto
        assert V.visible("transporte.reparto", vertical=e) is True
    assert V.visible("transporte.reparto", vertical="BAKERY") is False
