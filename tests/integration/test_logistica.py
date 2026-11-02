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
    # Documento EN PREPARACION (pendiente de picking/expedición); palé y línea PENDIENTE;
    # nada recibido aún. Solo `confirmar_picking_y_expedir` transiciona a EN TRANSITO.
    assert _estado_doc(db, id_doc) == "EN PREPARACION"
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
    assert _estado_doc(db, id_doc) == "EN PREPARACION"  # sin cambios


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


# ── GUI · el slot de recepción enruta al MOTOR OFICIAL (regresión de bug) ─────
def test_gui_slot_recepcion_actualiza_stock_via_motor_oficial(db, fab, monkeypatch):
    """Regresión de bug real: la pantalla de recepción tenía una copia INLINE y ROTA del alta de stock
    (código muerto tras un `continue`) que dejaba el stock intacto y marcaba TODO como "no encontrado".
    Ahora `procesar_confirmacion_recepcion` delega en `procesar_recepcion_logistica`, así que SÍ suma
    stock. Se invoca el slot con un `self` mínimo (sin ventana Qt) y las ayudas de UI parcheadas.
    """
    from src.gui import recepcion_pale as RP

    cod = fab.articulo(stock_total=0, stock_tienda=0)
    id_doc, pales = _crear_traspaso(db, fab, {"P1": _pale(cod, 8)}, destino="TIENDAR1")

    mensajes, marcados = [], []
    monkeypatch.setattr(RP, "_mensaje_ui", lambda *a, **k: mensajes.append(a))
    monkeypatch.setattr(RP, "_reab_marcar_articulos_recibidos", lambda cods: marcados.extend(cods))
    monkeypatch.setattr(RP, "DialogoNuevosArticulos",
                        lambda *a, **k: type("_D", (), {"exec": lambda self: None})())

    class _FakeWin:
        codigo_local = "TIENDAR1"
        usuario = "RECEPTOR"
        btn_nav_historial = None

        def __init__(self):
            self.redirigido = None

        def cambiar_vista(self, idx, btn=None):
            self.redirigido = idx

    win = _FakeWin()
    RP.RecepcionPaleWindow.procesar_confirmacion_recepcion(win, pales[0], [[cod, "Art", 8]])

    assert _stock(db, cod) == (8, 8)                 # el bug dejaba (0, 0)
    assert cod.upper() in marcados                    # propuesta marcada como recibida
    assert win.redirigido == 5                        # redirige al historial
    assert _estado_doc(db, id_doc) == "RECIBIDO"      # documento cerrado por el motor oficial


def test_gui_slot_recepcion_destino_incorrecto_no_suma_stock(db, fab, monkeypatch):
    """Destino incorrecto: el slot muestra el aviso y NO toca stock ni redirige."""
    from src.gui import recepcion_pale as RP

    cod = fab.articulo(stock_total=0, stock_tienda=0)
    _id, pales = _crear_traspaso(db, fab, {"P1": _pale(cod, 5)}, destino="TIENDAR1")

    titulos = []
    monkeypatch.setattr(RP, "_mensaje_ui", lambda parent, titulo, *a, **k: titulos.append(titulo))
    monkeypatch.setattr(RP, "_reab_marcar_articulos_recibidos", lambda cods: None)

    class _FakeWin:
        codigo_local = "OTRO_CENTRO"
        usuario = "RECEPTOR"
        btn_nav_historial = None

        def __init__(self):
            self.redirigido = None

        def cambiar_vista(self, idx, btn=None):
            self.redirigido = idx

    win = _FakeWin()
    RP.RecepcionPaleWindow.procesar_confirmacion_recepcion(win, pales[0], [[cod, "Art", 5]])

    assert _stock(db, cod) == (0, 0)
    assert win.redirigido is None
    assert any("Destino" in t for t in titulos)


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
    """En modo real sin lector accesible, conectar() devuelve False (sin excepción) — el gateway
    habla LLRP real vía `sllurp`; aquí se simula el fallo de conexión TCP al nivel de
    `LLRPReaderClient.connect` (mismo punto que usa `_conectar_llrp`)."""
    import sllurp.llrp as llrp
    import src.utils.rfid_gateway as RG

    def _boom(self, *a, **k):
        raise ConnectionRefusedError("sin hardware")

    monkeypatch.setattr(llrp.LLRPReaderClient, "connect", _boom)
    g = RG.LectorZebraGateway(ip="10.255.255.1", modo_simulado=False)
    assert g.conectar() is False


def test_rfid_sin_sllurp_instalado_no_conecta(monkeypatch):
    """Degradación honesta si `sllurp` no está instalado: conectar() devuelve False, nunca lanza
    ImportError hacia el llamador."""
    import src.utils.rfid_gateway as RG

    monkeypatch.setattr(RG, "_sllurp_disponible", lambda: False)
    g = RG.LectorZebraGateway(ip="10.0.0.5", modo_simulado=False)
    assert g.conectar() is False


def test_rfid_escribir_y_leer_tag_simulado_coinciden():
    """Lectura cruzada en simulado: tras escribir un EPC, `leer_tag()` devuelve ESE mismo EPC (no un
    valor fijo inventado) — la verificación `escribir_tag` → OK depende de esta coincidencia real."""
    from src.utils.rfid_gateway import LectorZebraGateway
    g = LectorZebraGateway(modo_simulado=True)
    assert g.leer_tag() is None  # nada grabado todavía
    assert g.escribir_tag("ABCDEF0123456789ABCDEF01") is True
    assert g.leer_tag() == "ABCDEF0123456789ABCDEF01"
    assert g._verificar_escritura("ABCDEF0123456789ABCDEF01") is True
    assert g._verificar_escritura("OTRO-EPC-DISTINTO") is False


def test_rfid_puerto_llrp_por_defecto():
    """`puerto` por defecto es el estándar LLRP 5084; aceptable sobrescribirlo."""
    from src.utils.rfid_gateway import PUERTO_LLRP_DEFECTO, LectorZebraGateway
    g = LectorZebraGateway(ip="10.0.0.5", modo_simulado=False)
    assert g.puerto == 5084 == PUERTO_LLRP_DEFECTO
    g2 = LectorZebraGateway(ip="10.0.0.5", modo_simulado=False, puerto=1234)
    assert g2.puerto == 1234


def test_rfid_llrp_leer_tag_y_verificar_escritura_real(monkeypatch):
    """Modo real (LLRP): `leer_tag()`/`_verificar_escritura()` se apoyan en el callback de
    tag-report de `sllurp` — un `LLRPReaderClient` falso dispara ese callback con un EPC conocido
    en cuanto se registra, simulando un tag ya presente en el campo del lector."""
    import sllurp.llrp as llrp
    import src.utils.rfid_gateway as RG

    class _ClienteFalso:
        def __init__(self, host, port, config, timeout=5.0):
            pass

        def connect(self):
            pass

        def add_tag_report_callback(self, cb):
            cb(self, [{"EPC": b"EPC1234REAL0000000000AB"}])

        def disconnect(self):
            pass

        def join(self, timeout=None):
            pass

    monkeypatch.setattr(llrp, "LLRPReaderClient", _ClienteFalso)
    g = RG.LectorZebraGateway(ip="10.0.0.5", modo_simulado=False)
    assert g.leer_tag() == "EPC1234REAL0000000000AB"
    assert g._verificar_escritura("EPC1234REAL0000000000AB") is True
    assert g._verificar_escritura("OTRO-EPC") is False


def test_rfid_llrp_leer_tag_sin_respuesta_da_none(monkeypatch):
    """Si el lector no reporta ningún tag dentro del timeout, `leer_tag()` degrada a `None` —
    nunca inventa un EPC."""
    import sllurp.llrp as llrp
    import src.utils.rfid_gateway as RG

    class _ClienteSinTags:
        def __init__(self, host, port, config, timeout=5.0):
            pass

        def connect(self):
            pass

        def add_tag_report_callback(self, cb):
            pass  # nunca dispara: nada en el campo del lector

        def disconnect(self):
            pass

        def join(self, timeout=None):
            pass

    monkeypatch.setattr(llrp, "LLRPReaderClient", _ClienteSinTags)
    g = RG.LectorZebraGateway(ip="10.0.0.5", modo_simulado=False)
    assert g.leer_tag() is None


def test_rfid_llrp_escribir_tag_confirma_y_verifica(monkeypatch):
    """Escritura real completa: `start_access_spec` confirma `C1G2WriteOpSpecResult.Result==0` →
    `escribir_tag` hace además la relectura cruzada (otra conexión) y la encuentra coincidente."""
    import sllurp.llrp as llrp
    import src.utils.rfid_gateway as RG

    epc = "AABBCCDDEEFF00112233AABB"  # 24 hex = 12 bytes = 96 bits

    class _ClienteEscritura:
        def __init__(self, host, port, config, timeout=5.0):
            self._cb = None

        def connect(self):
            pass

        def add_tag_report_callback(self, cb):
            self._cb = cb

        def start_access_spec(self, op_spec, target_spec=None, stop_after_count=0, access_spec_id=1):
            self._cb(self, [{"C1G2WriteOpSpecResult": {"Result": 0}}])

        def disconnect(self):
            pass

        def join(self, timeout=None):
            pass

    class _ClienteRelectura(_ClienteEscritura):
        def add_tag_report_callback(self, cb):
            cb(self, [{"EPC": epc.encode("ascii")}])

    secuencia = iter([_ClienteEscritura, _ClienteRelectura])
    monkeypatch.setattr(
        llrp, "LLRPReaderClient",
        lambda host, port, config, timeout=5.0: next(secuencia)(host, port, config, timeout))
    g = RG.LectorZebraGateway(ip="10.0.0.5", modo_simulado=False)
    assert g.escribir_tag(epc) is True


def test_rfid_llrp_escribir_tag_rechazado_por_el_chip(monkeypatch):
    """`C1G2WriteOpSpecResult.Result != 0` (chip ausente/rechazo) → `escribir_tag` devuelve False,
    sin lanzar y sin intentar una relectura de verificación inútil."""
    import sllurp.llrp as llrp
    import src.utils.rfid_gateway as RG

    class _ClienteRechazo:
        def __init__(self, host, port, config, timeout=5.0):
            self._cb = None

        def connect(self):
            pass

        def add_tag_report_callback(self, cb):
            self._cb = cb

        def start_access_spec(self, op_spec, target_spec=None, stop_after_count=0, access_spec_id=1):
            self._cb(self, [{"C1G2WriteOpSpecResult": {"Result": 1}}])

        def disconnect(self):
            pass

        def join(self, timeout=None):
            pass

    monkeypatch.setattr(llrp, "LLRPReaderClient", _ClienteRechazo)
    g = RG.LectorZebraGateway(ip="10.0.0.5", modo_simulado=False)
    assert g.escribir_tag("AABBCCDDEEFF00112233AABB") is False


def test_rfid_llrp_escribir_tag_epc_invalido_falla_honesto():
    """Un EPC que no es hex de 96 bits se rechaza ANTES de intentar conectar con el lector."""
    from src.utils.rfid_gateway import LectorZebraGateway
    g = LectorZebraGateway(ip="10.0.0.5", modo_simulado=False)
    assert g.escribir_tag("no-es-hex") is False
    assert g.escribir_tag("AABB") is False  # muy corto: no son 96 bits


def test_rfid_llrp_inventario_conteo_resuelve_epc_a_articulo(monkeypatch, fab, db):
    """Barrido real: agrega EPC distintos vistos y los resuelve a código de artículo vía
    `db.ubicaciones.obtener_por_epc` (la misma tabla que usa el resto del ERP, sin mapeo propio)."""
    import sllurp.llrp as llrp
    import src.utils.rfid_gateway as RG
    from src.db import ubicaciones as ubi_db

    emp = fab.empresa("RFID INVENTARIO LLRP")
    codigo = fab.articulo(id_empresa=emp, nombre="Producto Inventario LLRP")
    ubi_db.registrar_etiqueta_rfid("EPCINVENTARIOAAAA0000001", codigo, 1, id_empresa=emp)

    def _limpiar_ubicacion():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ubicaciones WHERE codigo_articulo=%s", (codigo,))
            conn.commit()
    fab.al_limpiar(_limpiar_ubicacion)

    class _ClienteInventario:
        def __init__(self, host, port, config, timeout=5.0):
            pass

        def connect(self):
            pass

        def add_tag_report_callback(self, cb):
            cb(self, [{"EPC": b"EPCINVENTARIOAAAA0000001"},
                     {"EPC": b"EPCINVENTARIOAAAA0000001"},  # mismo EPC repetido: no duplica unidad
                     {"EPC": b"EPC-SIN-ARTICULO-ASOCIADO"}])  # EPC desconocido: se ignora, honesto

        def disconnect(self):
            pass

        def join(self, timeout=None):
            pass

    monkeypatch.setattr(llrp, "LLRPReaderClient", _ClienteInventario)
    g = RG.LectorZebraGateway(ip="10.0.0.5", modo_simulado=False)
    conteo = g.inventario_conteo(duracion_seg=0.5)
    assert conteo == {codigo: 1}
