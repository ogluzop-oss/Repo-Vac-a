"""
Delegación a SOMA — los 4 tipos nuevos de esta entrega (ampliación pedida por el usuario más allá
de los 3 casos originales): autorrelleno GENÉRICO de Clientes/Proveedores (no solo Centros),
respuesta automática a tickets de Posventa y generación de pedidos de Compras. Mismo criterio de
honestidad/grounding que el resto del motor: la IA mockeada, nunca se llama a Anthropic de verdad.
"""

import pytest

from src.db.conexion import obtener_conexion
from src.services import eventos as EV
from src.services.soma_delegacion import historial as H
from src.services.soma_delegacion import motor as M
from src.services.soma_delegacion import reglas as R

pytestmark = pytest.mark.db


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM soma_delegaciones_historial WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM soma_delegaciones WHERE id_empresa=%s", (emp,))
        conn.commit()


def _mock_ia_json(monkeypatch, texto_respuesta):
    class _Bloque:
        type = "text"
        text = texto_respuesta

    class _Resp:
        content = [_Bloque()]

    monkeypatch.setattr("src.services.copilot.motor_llm._cliente",
                        lambda: type("C", (), {"messages": type("M", (), {
                            "create": staticmethod(lambda **kw: _Resp())})()})())
    monkeypatch.setattr("src.services.ia_control_uso.ejecutar_tarea_ia",
                        lambda eid, uid, tarea, fn: fn())


# ── Autorrelleno de Cliente ───────────────────────────────────────────────────
def test_autorrelleno_cliente_rellena_solo_vacios(fab, emp, monkeypatch):
    from src.db import clientes as cli_db
    cid = cli_db.crear_cliente("Cliente Autorrelleno", id_empresa=emp)   # pais/condiciones vacíos
    cli_db.actualizar_cliente(cid, id_empresa=emp, provincia="Barcelona")  # ESTE no se debe tocar
    R.crear_regla("configuracion.autorrelleno_cliente",
                  "Clientes nuevos de España, pago a 30 días.", id_empresa=emp)
    _mock_ia_json(monkeypatch, '{"pais": "ESPAÑA", "condiciones_pago": "30 días", '
                              '"provincia": "NO_DEBERIA_APLICARSE"}')
    resultados = M.procesar_evento("configuracion.autorrelleno_cliente", {"id_cliente": cid},
                                   id_empresa=emp)
    assert resultados[0]["estado"] == "aplicado"
    cliente = cli_db.obtener_cliente(cid)
    assert cliente["pais"] == "ESPAÑA"
    assert cliente["condiciones_pago"] == "30 días"
    assert cliente["provincia"] == "Barcelona"   # NUNCA sobrescrito, ya tenía valor
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM clientes WHERE id=%s", (cid,))
        conn.commit()


def test_autorrelleno_cliente_ya_completo_descarta(fab, emp):
    from src.db import clientes as cli_db
    cid = cli_db.crear_cliente("Cliente Completo", id_empresa=emp, pais="ESPAÑA",
                               provincia="Madrid", poblacion="Madrid")
    cli_db.actualizar_cliente(cid, id_empresa=emp, condiciones_pago="30 días",
                              regimen_fiscal="general")
    R.crear_regla("configuracion.autorrelleno_cliente", "Rellena datos.", id_empresa=emp)
    resultados = M.procesar_evento("configuracion.autorrelleno_cliente", {"id_cliente": cid},
                                   id_empresa=emp)
    assert resultados[0]["estado"] == "descartado"
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM clientes WHERE id=%s", (cid,))
        conn.commit()


def test_autorrelleno_cliente_de_otra_empresa_falla_honesto(fab, emp):
    from src.db import clientes as cli_db
    otra = fab.empresa("OTRA EMPRESA AUTORRELLENO")
    cid = cli_db.crear_cliente("Cliente Otra Empresa", id_empresa=otra)
    R.crear_regla("configuracion.autorrelleno_cliente", "x", id_empresa=emp)
    resultados = M.procesar_evento("configuracion.autorrelleno_cliente", {"id_cliente": cid},
                                   id_empresa=emp)
    assert resultados[0]["estado"] == "error"
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM clientes WHERE id=%s", (cid,))
        conn.commit()


# ── Autorrelleno de Proveedor ──────────────────────────────────────────────────
def test_autorrelleno_proveedor_rellena_solo_vacios(fab, emp, monkeypatch):
    from src.db import proveedores as prov_db
    pid = prov_db.crear_proveedor("Proveedor Autorrelleno", id_empresa=emp)
    prov_db.actualizar_proveedor(pid, id_empresa=emp, divisa="USD")   # ESTE no se debe tocar
    R.crear_regla("configuracion.autorrelleno_proveedor",
                  "Proveedores nacionales: 60 días, EUR.", id_empresa=emp)
    _mock_ia_json(monkeypatch,
                  '{"plazo_pago": 60, "forma_pago": "transferencia", "divisa": "EUR"}')
    resultados = M.procesar_evento("configuracion.autorrelleno_proveedor",
                                   {"id_proveedor": pid}, id_empresa=emp)
    assert resultados[0]["estado"] == "aplicado"
    proveedor = prov_db.obtener_proveedor(pid, id_empresa=emp)
    assert int(proveedor["plazo_pago"]) == 60
    assert proveedor["forma_pago"] == "transferencia"
    assert proveedor["divisa"] == "USD"   # NUNCA sobrescrito
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM proveedores WHERE id_proveedor=%s", (pid,))
        conn.commit()


def test_proveedor_creado_publica_evento(emp):
    from src.db import proveedores as prov_db
    vistos = []
    handler = lambda ev: vistos.append(ev)
    EV.suscribir("PROVEEDOR_CREADO", handler)
    try:
        pid = prov_db.crear_proveedor("Proveedor Evento", id_empresa=emp)
        assert any(str(ev.get("ref_id")) == str(pid) for ev in vistos)
    finally:
        EV.desuscribir("PROVEEDOR_CREADO", handler)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM proveedores WHERE id_proveedor=%s", (pid,))
            conn.commit()


# ── SAT: responder ticket ──────────────────────────────────────────────────────
def test_sat_responde_ticket_en_modo_automatico(fab, emp, monkeypatch):
    from src.services.sat import tickets
    tid = tickets.crear_ticket("¿Cómo hago una devolución?",
                               descripcion="Compré hace una semana y quiero devolverlo.",
                               id_empresa=emp)
    R.crear_regla("sat.responder_ticket", "Responde a preguntas de devolución.",
                  modo_aplicacion="automatico", id_empresa=emp)
    _mock_ia_json(monkeypatch,
                  '{"aplica": true, "motivo": "pregunta de devolución", '
                  '"respuesta": "Tienes 30 días para devoluciones, aquí el enlace."}')
    resultados = M.procesar_evento("sat.responder_ticket",
                                   {"id_ticket": tid, "asunto": "¿Cómo hago una devolución?",
                                    "descripcion": "Compré hace una semana y quiero devolverlo.",
                                    "categoria": None}, id_empresa=emp)
    assert resultados[0]["estado"] == "aplicado"
    comentarios = tickets.listar_comentarios(tid, id_empresa=emp)
    assert len(comentarios) == 1 and comentarios[0]["autor"] == "SOMA"
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ticket_comentarios WHERE id_ticket=%s", (tid,))
        cur.execute("DELETE FROM tickets WHERE id=%s", (tid,))
        conn.commit()


def test_sat_descarta_ticket_que_no_encaja(fab, emp, monkeypatch):
    from src.services.sat import tickets
    tid = tickets.crear_ticket("Mi pedido llegó roto", descripcion="El producto llegó dañado.",
                               id_empresa=emp)
    R.crear_regla("sat.responder_ticket", "Responde solo a preguntas de devolución.",
                  modo_aplicacion="automatico", id_empresa=emp)
    _mock_ia_json(monkeypatch, '{"aplica": false, "motivo": "es una incidencia de transporte"}')
    resultados = M.procesar_evento("sat.responder_ticket",
                                   {"id_ticket": tid, "asunto": "Mi pedido llegó roto",
                                    "descripcion": "El producto llegó dañado.", "categoria": None},
                                   id_empresa=emp)
    assert resultados[0]["estado"] == "descartado"
    assert tickets.listar_comentarios(tid, id_empresa=emp) == []
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM tickets WHERE id=%s", (tid,))
        conn.commit()


def test_ticket_creado_publica_evento(emp):
    from src.services.sat import tickets
    vistos = []
    handler = lambda ev: vistos.append(ev)
    EV.suscribir("TICKET_CREADO", handler)
    try:
        tid = tickets.crear_ticket("Ticket de prueba evento", id_empresa=emp)
        assert any(str(ev.get("ref_id")) == str(tid) for ev in vistos)
    finally:
        EV.desuscribir("TICKET_CREADO", handler)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM tickets WHERE id=%s", (tid,))
            conn.commit()


# ── Compras: generar pedido ────────────────────────────────────────────────────
def test_compras_genera_pedido_borrador_con_articulos_reales(fab, emp, monkeypatch):
    cod = fab.articulo(id_empresa=emp, nombre="Papel A4", precio=4.5)
    from src.db import proveedores as prov_db
    pid = prov_db.crear_proveedor("Proveedor Papelería", id_empresa=emp)
    R.crear_regla("compras.generar_pedido", "Pide en cajas completas.", id_empresa=emp)
    _mock_ia_json(monkeypatch,
                  f'{{"lineas": [{{"codigo": "{cod}", "cantidad": 10, "precio_unitario": 4.5}}], '
                  '"observaciones": "Pedido generado por SOMA"}')
    resultados = M.procesar_evento(
        "compras.generar_pedido", {"id_proveedor": pid, "brief": "papel A4 para la oficina"},
        id_empresa=emp)
    assert resultados[0]["estado"] == "aplicado"
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_pedido, estado, total FROM compras_pedidos WHERE id_empresa=%s "
                   "AND id_proveedor=%s ORDER BY id_pedido DESC LIMIT 1", (emp, pid))
        fila = cur.fetchone()
        assert fila is not None
        pedido_id, estado, total = fila if not isinstance(fila, dict) else \
            (fila["id_pedido"], fila["estado"], fila["total"])
        assert estado == "BORRADOR"
        assert float(total) == 45.0
        cur.execute("DELETE FROM compras_pedidos_lineas WHERE id_pedido=%s", (pedido_id,))
        cur.execute("DELETE FROM compras_pedidos WHERE id_pedido=%s", (pedido_id,))
        cur.execute("DELETE FROM proveedores WHERE id_proveedor=%s", (pid,))
        conn.commit()


def test_compras_rechaza_proveedor_bloqueado(fab, emp, monkeypatch):
    cod = fab.articulo(id_empresa=emp, nombre="Tóner impresora", precio=30.0)
    from src.db import proveedores as prov_db
    pid = prov_db.crear_proveedor("Proveedor Bloqueado", id_empresa=emp)
    prov_db.bloquear(pid, True, id_empresa=emp)
    R.crear_regla("compras.generar_pedido", "x", id_empresa=emp)
    resultados = M.procesar_evento(
        "compras.generar_pedido", {"id_proveedor": pid, "brief": "tóner impresora"}, id_empresa=emp)
    assert resultados[0]["estado"] == "descartado"
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM proveedores WHERE id_proveedor=%s", (pid,))
        conn.commit()


def test_compras_rechaza_codigo_inventado(fab, emp, monkeypatch):
    fab.articulo(id_empresa=emp, nombre="Grapadora", precio=8.0)
    from src.db import proveedores as prov_db
    pid = prov_db.crear_proveedor("Proveedor Honestidad", id_empresa=emp)
    R.crear_regla("compras.generar_pedido", "Nunca inventes artículos.", id_empresa=emp)
    _mock_ia_json(monkeypatch,
                  '{"lineas": [{"codigo": "NO-EXISTE-999", "cantidad": 1, "precio_unitario": 1}], '
                  '"observaciones": "x"}')
    resultados = M.procesar_evento(
        "compras.generar_pedido", {"id_proveedor": pid, "brief": "grapadora"}, id_empresa=emp)
    assert resultados[0]["estado"] == "descartado"
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM compras_pedidos WHERE id_empresa=%s AND id_proveedor=%s",
                   (emp, pid))
        total = cur.fetchone()
        total = total[0] if not isinstance(total, dict) else list(total.values())[0]
        assert total == 0
        cur.execute("DELETE FROM proveedores WHERE id_proveedor=%s", (pid,))
        conn.commit()


def test_catalogo_lista_7_tipos_con_pantallas_correctas():
    from src.services.soma_delegacion import catalogo as CAT
    por_codigo = {t["codigo"]: t["pantalla"] for t in CAT.listar()}
    assert por_codigo == {
        "correo.responder_automatico": "correo",
        "crm.generar_presupuesto": "crm",
        "configuracion.autorrelleno_centro": "configuracion",
        "configuracion.autorrelleno_cliente": "crm",
        "configuracion.autorrelleno_proveedor": "compras_avanzado",
        "sat.responder_ticket": "sat",
        "compras.generar_pedido": "compras_avanzado",
    }
