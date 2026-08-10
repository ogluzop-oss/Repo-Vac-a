"""
Tests PCD · Fase 10 (omnicanalidad): TPV/ventas proyectan a la Transacción Comercial (núcleo único) +
deprecación de la superficie legacy /pedidos.

Verifica: la venta canónica (`registrar_venta_con_items`) proyecta a la Transacción Comercial
(write-through no bloqueante e idempotente); todos los canales convergen en la MISMA Transacción
(origen distingue TPV/web); la ruta legacy /pedidos sigue funcionando pero marcada @deprecated; sin
motores nuevos ni regresión.
"""

import inspect

import pytest

EMP = "T-OMNI-A"


@pytest.fixture()
def limpio(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("transaccion_decisiones", "transaccion_eventos", "transaccion_lineas",
                  "transaccion_comercial"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE vi FROM venta_items vi JOIN ventas v ON v.id=vi.venta_id "
                    "WHERE v.id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM ventas WHERE id_empresa=%s", (EMP,))
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("transaccion_decisiones", "transaccion_eventos", "transaccion_lineas",
                  "transaccion_comercial"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE vi FROM venta_items vi JOIN ventas v ON v.id=vi.venta_id "
                    "WHERE v.id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM ventas WHERE id_empresa=%s", (EMP,))
        conn.commit()


def _venta(db, total=20.0):
    """Inserta una venta + ítem directamente (simula el registro canónico) y devuelve venta_id."""
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO ventas (fecha, total, forma_pago, id_empresa, id_tienda) "
                    "VALUES (NOW(), %s, 'efectivo', %s, 0)", (total, EMP))
        vid = cur.lastrowid
        cur.execute("INSERT INTO venta_items (venta_id, codigo_articulo, nombre, cantidad, "
                    "precio_unitario, subtotal, id_empresa) VALUES (%s,'ART1','Item',2,10,%s,%s)",
                    (vid, total, EMP))
        conn.commit()
    return vid


def test_venta_proyecta_a_transaccion(limpio, db):
    from src.services.comercio_digital import transacciones as tx
    vid = _venta(db)
    tid = tx.desde_venta(vid, origen="tpv", id_empresa=EMP)
    assert tid
    t = tx.obtener(tid, EMP)
    assert t["origen"] == "tpv" and t["estado"] == "PAGADA" and t["tipo"] == "pedido"
    assert t["referencia_externa"] == f"venta:{vid}"


def test_proyeccion_idempotente(limpio, db):
    from src.services.comercio_digital import transacciones as tx
    vid = _venta(db)
    t1 = tx.desde_venta(vid, id_empresa=EMP)
    t2 = tx.desde_venta(vid, id_empresa=EMP)          # segunda vez → misma Transacción (no duplica)
    assert t1 == t2
    assert len(tx.listar(EMP, origen="tpv")) == 1


def test_omnicanal_mismo_nucleo_distinto_origen(limpio, db):
    """TPV y web proyectan en la MISMA entidad (Transacción Comercial), distinguidas por `origen`."""
    from src.services.comercio_digital import transacciones as tx
    vid = _venta(db)
    tx.desde_venta(vid, origen="tpv", id_empresa=EMP)
    tx.crear(tipo="pedido", origen="web", estado="PAGADA", id_empresa=EMP,
             lineas=[{"codigo": "ART1", "cantidad": 1, "precio_unitario": 5}])
    origenes = {t["origen"] for t in tx.listar(EMP)}
    assert {"tpv", "web"} <= origenes                 # mismo modelo único, varios canales


def test_proyectar_dispatcher(limpio, db):
    from src.services.comercio_digital import transacciones as tx
    vid = _venta(db)
    assert tx.proyectar("tpv", venta_id=vid, id_empresa=EMP)     # delega en desde_venta
    assert tx.proyectar("tpv") is None                            # sin referencia → None


def test_registrar_venta_con_items_proyecta(limpio, db):
    """La ruta canónica de venta dispara la proyección (write-through no bloqueante)."""
    from src.db.conexion import registrar_venta_con_items
    from src.services.comercio_digital import transacciones as tx
    vid = registrar_venta_con_items(
        [{"codigo_articulo": "ART1", "nombre": "Item", "cantidad": 1, "precio_unitario": 10,
          "subtotal": 10}], forma_pago="efectivo", total=10.0, id_empresa=EMP, id_tienda=0)
    assert vid
    # La venta quedó proyectada en la Transacción Comercial (best-effort, ya ejecutado).
    ts = tx.listar(EMP, origen="tpv")
    assert any(t["referencia_externa"] == f"venta:{vid}" for t in ts)


def test_pedidos_legacy_deprecado():
    import src.backend.api as api
    src = inspect.getsource(api)
    assert "@deprecated" in src and "Deprecation" in src and "successor-version" in src
    # No se elimina (Strangler): las rutas siguen registradas.
    assert '@bp.get("/pedidos")' in src and "listar_pedidos_online" in src


def test_sin_motor_nuevo_ni_regresion_en_core():
    """Fase 10 reutiliza `crear` (modelo único); no introduce entidades/tablas nuevas."""
    from src.services.comercio_digital import transacciones as tx
    src = inspect.getsource(tx.desde_venta) + inspect.getsource(tx.proyectar)
    assert "CREATE TABLE" not in src and "crear(" in src        # reutiliza el núcleo
    d = tx.descriptor()
    assert d  # el servicio sigue operativo
