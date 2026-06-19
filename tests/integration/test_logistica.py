"""
R1 · Robustez logística — cobertura de flujos críticos (sin cambios funcionales).

Cubre: traspasos (alta/historial/trazabilidad), recepción completa/parcial,
estados, movimientos de stock, destino incorrecto, palé ya recibido (idempotencia),
artículo no encontrado, integridad de stock, incidencias y RFID (simulado / sin HW).

Todos los tests usan la BD de pruebas (`*_test`) y la fábrica con limpieza.
"""

import pytest

pytestmark = pytest.mark.db


# ── utilidades de apoyo ───────────────────────────────────────────────────────
def _limpia_doc(db, id_documento):
    """Borra todo el rastro de un documento logístico de prueba."""
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for sql in (
            "DELETE FROM movimientos_stock WHERE id_documento=%s",
            "DELETE FROM recepciones_logisticas WHERE id_documento=%s",
            "DELETE FROM incidencias_logisticas WHERE id_documento=%s",
            "DELETE FROM documentos_logisticos_lineas WHERE id_documento=%s",
            "DELETE FROM documentos_logisticos_pales WHERE id_documento=%s",
            "DELETE FROM documentos_logisticos WHERE id_documento=%s",
        ):
            cur.execute(sql, (id_documento,))
        conn.commit()


def _crear_traspaso(db, fab, pales, origen="ALMACEN", destino="TIENDAR1"):
    """Da de alta un traspaso real y registra su limpieza. Devuelve (id_doc, pales[])."""
    from src.db import logistica as L
    res = L.guardar_traspaso_logistico(
        origen=origen, destino=destino, usuario="TESTER",
        agencia="PROPIA", observaciones="r1", pales=pales)
    id_doc = res["id_documento"]
    fab.al_limpiar(lambda: _limpia_doc(db, id_doc))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_pale FROM documentos_logisticos_pales "
                    "WHERE id_documento=%s ORDER BY id_pale", (id_doc,))
        ids = [r[0] if not isinstance(r, dict) else r["id_pale"] for r in cur.fetchall()]
    return id_doc, ids


def _stock(db, codigo):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_total, Stock_tienda FROM articulos WHERE codigo=%s", (codigo,))
        r = cur.fetchone()
        if isinstance(r, dict):
            return r["Stock_total"], r["Stock_tienda"]
        return r[0], r[1]


def _estado_doc(db, id_doc):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado FROM documentos_logisticos WHERE id_documento=%s", (id_doc,))
        r = cur.fetchone()
        return (r[0] if not isinstance(r, dict) else r["estado"]) if r else None


def _pale(art_codigo, cantidad, nombre="Art", peso=10.0):
    return {"peso": peso, "articulos": [{"codigo": art_codigo, "nombre": nombre, "cantidad": cantidad}]}


# ── TRASPASOS ─────────────────────────────────────────────────────────────────
def test_alta_traspaso_estados_iniciales(db, fab):
    cod = fab.articulo(stock_total=0, stock_tienda=0)
    id_doc, pales = _crear_traspaso(db, fab, {"P1": _pale(cod, 5)})
    assert id_doc.startswith("TRA-") and len(pales) == 1
    # Documento EN TRANSITO; palé y línea PENDIENTE; nada recibido aún.
    assert _estado_doc(db, id_doc) == "EN TRANSITO"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado FROM documentos_logisticos_pales WHERE id_documento=%s", (id_doc,))
        assert (cur.fetchone() or [None])[0] == "PENDIENTE"
        cur.execute("SELECT cantidad_enviada, cantidad_recibida, estado_linea "
                    "FROM documentos_logisticos_lineas WHERE id_documento=%s", (id_doc,))
        fila = cur.fetchone()
        env, rec, est = tuple(fila.values()) if isinstance(fila, dict) else fila
        assert (env, rec, est) == (5, 0, "PENDIENTE")


def test_traspaso_sin_pales_rechazado(db, fab):
    from src.db import logistica as L
    with pytest.raises(ValueError):
        L.guardar_traspaso_logistico("ALMACEN", "TIENDAR1", "T", "PROPIA", "", {})


def test_historial_y_trazabilidad_listan_traspaso(db, fab):
    from src.db import logistica as L
    cod = fab.articulo()
    id_doc, _ = _crear_traspaso(db, fab, {"P1": _pale(cod, 3)})
    hist = L.obtener_historial_traspasos(estado_filtro="TODOS")
    assert any(h["id_documento"] == id_doc for h in hist)
    traz = L.obtener_trazabilidad_logistica()
    assert any(t["id_documento"] == id_doc for t in traz)


# ── RECEPCIONES ───────────────────────────────────────────────────────────────
def test_recepcion_completa_actualiza_stock_y_estados(db, fab):
    from src.db import logistica as L
    cod = fab.articulo(stock_total=0, stock_tienda=0)
    id_doc, pales = _crear_traspaso(db, fab, {"P1": _pale(cod, 10)})
    r = L.procesar_recepcion_logistica(pales[0], "TIENDAR1", "RECEPTOR",
                                       [{"codigo": cod, "nombre": "Art", "cantidad": 10}])
    assert r["ok"] is True and r["count_actualizados"] == 1
    assert _stock(db, cod) == (10, 10)                 # stock incrementado
    assert _estado_doc(db, id_doc) == "RECIBIDO"        # único palé recibido
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado_linea, cantidad_recibida FROM documentos_logisticos_lineas "
                    "WHERE id_documento=%s", (id_doc,))
        est, rec = cur.fetchone()
        assert (est, rec) == ("RECIBIDO", 10)
        cur.execute("SELECT tipo_movimiento, cantidad FROM movimientos_stock WHERE id_documento=%s", (id_doc,))
        tipo, cant = cur.fetchone()
        assert tipo == "ENTRADA_TRASPASO" and cant == 10
        cur.execute("SELECT total_unidades FROM recepciones_logisticas WHERE id_documento=%s", (id_doc,))
        assert cur.fetchone()[0] == 10


def test_recepcion_parcial_por_palmes_documento_en_parcial(db, fab):
    """2 palés, se recibe 1 → documento queda PARCIAL y solo sube el stock recibido."""
    from src.db import logistica as L
    cod = fab.articulo(stock_total=0, stock_tienda=0)
    id_doc, pales = _crear_traspaso(db, fab, {"P1": _pale(cod, 4), "P2": _pale(cod, 6)})
    assert len(pales) == 2
    L.procesar_recepcion_logistica(pales[0], "TIENDAR1", "RECEPTOR",
                                   [{"codigo": cod, "cantidad": 4}])
    assert _estado_doc(db, id_doc) == "PARCIAL"
    assert _stock(db, cod) == (4, 4)


def test_recepcion_parcial_de_linea(db, fab):
    """Se recibe menos cantidad de la enviada en la línea → línea PARCIAL."""
    from src.db import logistica as L
    cod = fab.articulo(stock_total=0, stock_tienda=0)
    id_doc, pales = _crear_traspaso(db, fab, {"P1": _pale(cod, 10)})
    L.procesar_recepcion_logistica(pales[0], "TIENDAR1", "RECEPTOR",
                                   [{"codigo": cod, "cantidad": 4}])
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado_linea, cantidad_recibida FROM documentos_logisticos_lineas "
                    "WHERE id_documento=%s", (id_doc,))
        est, rec = cur.fetchone()
    assert est == "PARCIAL" and rec == 4
    assert _stock(db, cod) == (4, 4)


def test_recepcion_destino_incorrecto_no_toca_stock(db, fab):
    from src.db import logistica as L
    cod = fab.articulo(stock_total=0, stock_tienda=0)
    id_doc, pales = _crear_traspaso(db, fab, {"P1": _pale(cod, 7)})
    r = L.procesar_recepcion_logistica(pales[0], "OTRO_CENTRO", "RECEPTOR",
                                       [{"codigo": cod, "cantidad": 7}])
    assert r["ok"] is False and r["motivo"] == "destino_incorrecto"
    assert _stock(db, cod) == (0, 0)                    # sin cambios
    assert _estado_doc(db, id_doc) == "EN TRANSITO"


def test_recepcion_idempotente_pale_ya_recibido(db, fab):
    from src.db import logistica as L
    cod = fab.articulo(stock_total=0, stock_tienda=0)
    _id, pales = _crear_traspaso(db, fab, {"P1": _pale(cod, 5)})
    L.procesar_recepcion_logistica(pales[0], "TIENDAR1", "R", [{"codigo": cod, "cantidad": 5}])
    r2 = L.procesar_recepcion_logistica(pales[0], "TIENDAR1", "R", [{"codigo": cod, "cantidad": 5}])
    assert r2["ok"] is False and r2["motivo"] == "pale_ya_recibido"
    assert _stock(db, cod) == (5, 5)                    # NO se duplica


def test_recepcion_articulo_no_encontrado_genera_incidencia(db, fab):
    from src.db import logistica as L
    id_doc, pales = _crear_traspaso(db, fab, {"P1": _pale("INEXISTENTE_R1", 3, nombre="Fantasma")})
    r = L.procesar_recepcion_logistica(pales[0], "TIENDAR1", "R",
                                       [{"codigo": "INEXISTENTE_R1", "nombre": "Fantasma", "cantidad": 3}])
    assert r["ok"] is True
    assert any(a["ean"] == "INEXISTENTE_R1" for a in r["articulos_no_encontrados"])
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT incidencias FROM recepciones_logisticas WHERE id_documento=%s", (id_doc,))
        inc = cur.fetchone()[0]
        assert inc and "INEXISTENTE_R1" in inc          # incidencia persistida (JSON)
        cur.execute("SELECT COUNT(*) FROM movimientos_stock WHERE id_documento=%s", (id_doc,))
        assert cur.fetchone()[0] == 0                    # no hubo movimiento de stock


# ── INTEGRIDAD DE STOCK ───────────────────────────────────────────────────────
def test_cantidad_no_positiva_se_ignora(db, fab):
    from src.db import logistica as L
    cod = fab.articulo(stock_total=2, stock_tienda=2)
    id_doc, pales = _crear_traspaso(db, fab, {"P1": _pale(cod, 5)})
    r = L.procesar_recepcion_logistica(pales[0], "TIENDAR1", "R",
                                       [{"codigo": cod, "cantidad": 0},
                                        {"codigo": cod, "cantidad": -3}])
    assert r["ok"] is True and r["count_actualizados"] == 0
    assert _stock(db, cod) == (2, 2)                    # intacto, nunca negativo
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM movimientos_stock WHERE id_documento=%s", (id_doc,))
        assert cur.fetchone()[0] == 0


# ── INCIDENCIAS ───────────────────────────────────────────────────────────────
def test_incidencia_apertura_listado_cierre(db, fab):
    from src.services.logistics import logistics_service as S
    id_doc, _ = _crear_traspaso(db, fab, {"P1": _pale(fab.articulo(), 1)})
    iid = S.registrar_incidencia(id_doc, tipo="ROTURA", descripcion="caja dañada",
                                 usuario="T", cantidad_afectada=1)
    assert iid
    abiertas = S.listar_incidencias(estado="ABIERTA")
    assert any(i["id"] == iid and i["estado"] == "ABIERTA" for i in abiertas)
    assert S.cerrar_incidencia(iid) is True
    cerradas = S.listar_incidencias(estado="CERRADA")
    assert any(i["id"] == iid and i["estado"] == "CERRADA" for i in cerradas)


# ── RFID (sin dependencia de hardware) ────────────────────────────────────────
def test_rfid_modo_simulado_conecta():
    from src.utils.rfid_gateway import LectorZebraGateway
    g = LectorZebraGateway(modo_simulado=True)
    assert g.conectar() is True


def test_rfid_genera_epc_formato():
    from src.utils.rfid_gateway import LectorZebraGateway
    epc = LectorZebraGateway(modo_simulado=True).generar_epc_manual("REF-001")
    assert epc.startswith("3G0E")
    hexpart = epc[4:]
    assert len(hexpart) == 16 and all(c in "0123456789ABCDEF" for c in hexpart)


def test_rfid_sin_hardware_no_conecta(monkeypatch):
    """En modo real sin lector accesible, conectar() devuelve False (sin excepción)."""
    import src.utils.rfid_gateway as RG

    def _boom(*a, **k):
        raise RG.requests.exceptions.ConnectionError("sin hardware")

    monkeypatch.setattr(RG.requests, "get", _boom)
    g = RG.LectorZebraGateway(ip="10.255.255.1", modo_simulado=False)
    assert g.conectar() is False
