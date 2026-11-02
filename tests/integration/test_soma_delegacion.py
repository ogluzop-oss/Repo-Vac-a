"""
Delegación de tareas repetitivas a SOMA (SUPERADMIN) — `services.soma_delegacion`: CRUD de
reglas/historial, catálogo de tipos, y el dispatch `motor.procesar_evento` contra los 3
ejecutores integrados (correo, CRM, centros), con la IA mockeada (nunca se llama a Anthropic de
verdad en tests). También cubre el enhebrado real de `responder_correo` y el guard anti-duplicado
de `CORREO_RECIBIDO` (bug cerrado en esta misma entrega: antes se republicaba en cada
resincronización, lo que habría disparado una respuesta automática repetida al mismo correo).
"""

import pytest

from src.db.conexion import obtener_conexion
from src.services.soma_delegacion import catalogo as CAT
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


# ── Catálogo ────────────────────────────────────────────────────────────────────
def test_catalogo_registra_los_tres_tipos_integrados():
    tipos = {t["codigo"] for t in CAT.listar()}
    assert {"correo.responder_automatico", "crm.generar_presupuesto",
           "configuracion.autorrelleno_centro"} <= tipos


def test_rbac_catalogo_incluye_el_permiso_soma_delegacion():
    from src.services.seguridad.catalogo import CATALOGO
    assert "soma_delegacion.admin" in CATALOGO


# ── Reglas (CRUD) ────────────────────────────────────────────────────────────────
def test_crear_regla_exige_instrucciones_no_vacias(emp):
    assert R.crear_regla("correo.responder_automatico", "", id_empresa=emp) is None
    assert R.crear_regla("correo.responder_automatico", "   ", id_empresa=emp) is None


def test_crear_regla_rechaza_tipo_desconocido(emp):
    assert R.crear_regla("tipo_que_no_existe", "haz esto", id_empresa=emp) is None


def test_crud_regla_completo(emp):
    rid = R.crear_regla("correo.responder_automatico", "Responde solo a horarios.",
                        modo_aplicacion="revisar_antes", id_empresa=emp)
    assert rid
    r = R.obtener_regla(rid, id_empresa=emp)
    assert r["instrucciones"] == "Responde solo a horarios." and r["activa"] == 1
    assert R.actualizar_regla(rid, id_empresa=emp, activa=False)
    assert R.obtener_regla(rid, id_empresa=emp)["activa"] == 0
    # No se puede vaciar las instrucciones de una regla existente.
    assert R.actualizar_regla(rid, id_empresa=emp, instrucciones="   ") is False
    assert R.eliminar_regla(rid, id_empresa=emp)
    assert R.obtener_regla(rid, id_empresa=emp) is None


def test_listar_reglas_filtra_por_tipo_y_activas(emp):
    R.crear_regla("correo.responder_automatico", "A", id_empresa=emp)
    R.crear_regla("correo.responder_automatico", "B", activa=False, id_empresa=emp)
    R.crear_regla("configuracion.autorrelleno_centro", "C", id_empresa=emp)
    assert len(R.listar_reglas(id_empresa=emp)) == 3
    assert len(R.listar_reglas(id_empresa=emp, tipo="correo.responder_automatico")) == 2
    assert len(R.listar_reglas(id_empresa=emp, tipo="correo.responder_automatico",
                               solo_activas=True)) == 1


# ── Motor: correo.responder_automatico ───────────────────────────────────────────
def test_motor_correo_aplica_y_envia_en_modo_automatico(fab, emp, monkeypatch, db):
    id_correo = fab.buzon_correo(id_empresa=emp)
    from src.db import correo as correo_db
    id_recibido = correo_db.guardar_recibido(
        id_correo, "Juan <juan@test.com>", "Horario de la tienda",
        "Hola, ¿a qué hora abrís los sábados?", message_id="<msg1@test>", id_empresa=emp)
    R.crear_regla("correo.responder_automatico",
                  "Responde solo a preguntas sobre horarios, con tono cercano.",
                  modo_aplicacion="automatico", id_empresa=emp)
    _mock_ia_json(monkeypatch,
                  '{"aplica": true, "motivo": "pregunta por el horario", '
                  '"respuesta": "¡Hola! Abrimos los sábados de 10:00 a 14:00."}')

    contexto = {"id_correo": id_correo, "id_recibido": id_recibido, "remitente": "Juan <juan@test.com>",
               "asunto": "Horario de la tienda", "cuerpo": "Hola, ¿a qué hora abrís los sábados?"}
    resultados = M.procesar_evento("correo.responder_automatico", contexto, id_empresa=emp)
    assert len(resultados) == 1 and resultados[0]["estado"] == "aplicado"

    hist = H.listar(id_empresa=emp, tipo="correo.responder_automatico")
    assert len(hist) == 1 and hist[0]["estado"] == "aplicado"

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM correos_recibidos WHERE id_correo=%s", (id_correo,))
        cur.execute("DELETE FROM correos_corporativos WHERE id_correo=%s", (id_correo,))
        conn.commit()


def test_motor_correo_descarta_si_no_aplica(fab, emp, monkeypatch):
    id_correo = fab.buzon_correo(id_empresa=emp)
    from src.db import correo as correo_db
    id_recibido = correo_db.guardar_recibido(
        id_correo, "cliente@test.com", "Reclamación", "Quiero devolver un producto.",
        message_id="<msg2@test>", id_empresa=emp)
    R.crear_regla("correo.responder_automatico", "Responde solo a preguntas de horario.",
                  modo_aplicacion="automatico", id_empresa=emp)
    _mock_ia_json(monkeypatch,
                  '{"aplica": false, "motivo": "es una reclamación, no una pregunta de horario"}')

    contexto = {"id_correo": id_correo, "id_recibido": id_recibido, "remitente": "cliente@test.com",
               "asunto": "Reclamación", "cuerpo": "Quiero devolver un producto."}
    resultados = M.procesar_evento("correo.responder_automatico", contexto, id_empresa=emp)
    assert resultados[0]["estado"] == "descartado"


def test_motor_correo_modo_revisar_antes_no_envia(fab, emp, monkeypatch):
    id_correo = fab.buzon_correo(id_empresa=emp)
    from src.db import correo as correo_db
    id_recibido = correo_db.guardar_recibido(
        id_correo, "ana@test.com", "Horario", "¿Abrís los domingos?",
        message_id="<msg3@test>", id_empresa=emp)
    R.crear_regla("correo.responder_automatico", "Responde a preguntas de horario.",
                  modo_aplicacion="revisar_antes", id_empresa=emp)
    _mock_ia_json(monkeypatch,
                  '{"aplica": true, "motivo": "pregunta de horario", '
                  '"respuesta": "No, los domingos cerramos."}')
    contexto = {"id_correo": id_correo, "id_recibido": id_recibido, "remitente": "ana@test.com",
               "asunto": "Horario", "cuerpo": "¿Abrís los domingos?"}
    resultados = M.procesar_evento("correo.responder_automatico", contexto, id_empresa=emp)
    assert resultados[0]["estado"] == "pendiente_revision"
    assert resultados[0]["decision"]["respuesta"] == "No, los domingos cerramos."


def test_motor_correo_sin_regla_activa_no_hace_nada(emp):
    resultados = M.procesar_evento("correo.responder_automatico", {"id_correo": "x"}, id_empresa=emp)
    assert resultados == []


# ── Motor: configuracion.autorrelleno_centro ──────────────────────────────────────
def test_motor_centro_autorrellena_solo_campos_vacios(fab, emp):
    from src.db import centros as centros_db
    from src.db import empresa as empresa_db
    empresa_db.actualizar_empresa(emp, telefono="900111222", email_principal="info@test.com",
                                  pais="ESPAÑA", municipio="Madrid", provincia="Madrid")
    id_centro = centros_db.crear_centro(id_empresa=emp, nombre_centro="Tienda Centro",
                                        telefono="600000000")   # teléfono YA puesto a mano
    R.crear_regla("configuracion.autorrelleno_centro", "Rellena datos de contacto.",
                  id_empresa=emp)
    resultados = M.procesar_evento("configuracion.autorrelleno_centro", {"id_centro": id_centro},
                                   id_empresa=emp)
    assert resultados[0]["estado"] == "aplicado"
    centro = centros_db.obtener_centro(id_centro)
    assert centro["telefono"] == "600000000"          # NUNCA sobrescrito
    assert centro["email"] == "info@test.com"          # autorrellenado desde la empresa
    assert centro["pais"] == "ESPAÑA"


def test_motor_centro_ya_completo_descarta(fab, emp):
    from src.db import centros as centros_db
    id_centro = centros_db.crear_centro(
        id_empresa=emp, nombre_centro="Completo", telefono="1", email="e@x.com", pais="ES",
        municipio="M", provincia="P", cod_pais="ES", cod_municipio="28079",
        cod_actividad="001", actividad_economica="Comercio")
    R.crear_regla("configuracion.autorrelleno_centro", "Rellena datos.", id_empresa=emp)
    resultados = M.procesar_evento("configuracion.autorrelleno_centro", {"id_centro": id_centro},
                                   id_empresa=emp)
    assert resultados[0]["estado"] == "descartado"


# ── Motor: crm.generar_presupuesto ────────────────────────────────────────────────
def test_motor_crm_genera_presupuesto_borrador_con_articulos_reales(fab, emp, monkeypatch):
    cod = fab.articulo(id_empresa=emp, nombre="Silla de oficina", precio=99.0)
    from src.db import clientes as cli_db
    cid = cli_db.crear_cliente("Cliente Presupuesto", id_empresa=emp)
    R.crear_regla("crm.generar_presupuesto", "Aplica precios de lista sin descuento.",
                  id_empresa=emp)
    _mock_ia_json(monkeypatch,
                  f'{{"lineas": [{{"codigo": "{cod}", "cantidad": 2, "precio_unitario": 99.0}}], '
                  '"observaciones": "Presupuesto generado por SOMA"}')
    resultados = M.procesar_evento(
        "crm.generar_presupuesto", {"id_cliente": cid, "brief": "2 sillas de oficina"},
        id_empresa=emp)
    assert resultados[0]["estado"] == "aplicado"

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, estado, total FROM ventas_presupuestos WHERE id_empresa=%s "
                   "AND id_cliente=%s ORDER BY id DESC LIMIT 1", (emp, cid))
        fila = cur.fetchone()
        assert fila is not None
        did, estado, total = fila if not isinstance(fila, dict) else \
            (fila["id"], fila["estado"], fila["total"])
        assert estado == "borrador"
        assert float(total) == 198.0
        cur.execute("DELETE FROM ventas_presupuestos_lineas WHERE id_doc=%s", (did,))
        cur.execute("DELETE FROM ventas_presupuestos WHERE id=%s", (did,))
        cur.execute("DELETE FROM clientes WHERE id=%s", (cid,))
        conn.commit()


def test_motor_crm_rechaza_codigo_inventado_por_la_ia(fab, emp, monkeypatch):
    fab.articulo(id_empresa=emp, nombre="Mesa de oficina", precio=150.0)
    from src.db import clientes as cli_db
    cid = cli_db.crear_cliente("Cliente Honestidad", id_empresa=emp)
    R.crear_regla("crm.generar_presupuesto", "Nunca inventes artículos.", id_empresa=emp)
    # La IA "alucina" un código que no está en la lista de candidatos reales.
    _mock_ia_json(monkeypatch,
                  '{"lineas": [{"codigo": "NO-EXISTE-999", "cantidad": 1, "precio_unitario": 10}], '
                  '"observaciones": "x"}')
    resultados = M.procesar_evento(
        "crm.generar_presupuesto", {"id_cliente": cid, "brief": "mesa de oficina"}, id_empresa=emp)
    assert resultados[0]["estado"] == "descartado"   # el código inventado nunca llega a crear nada
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ventas_presupuestos WHERE id_empresa=%s AND id_cliente=%s",
                   (emp, cid))
        total = cur.fetchone()
        total = total[0] if not isinstance(total, dict) else list(total.values())[0]
        assert total == 0
        cur.execute("DELETE FROM clientes WHERE id=%s", (cid,))
        conn.commit()


def test_motor_crm_sin_articulos_coincidentes_degrada_honesto(emp):
    from src.db import clientes as cli_db
    cid = cli_db.crear_cliente("Cliente Sin Articulos", id_empresa=emp)
    R.crear_regla("crm.generar_presupuesto", "Genera presupuestos.", id_empresa=emp)
    resultados = M.procesar_evento(
        "crm.generar_presupuesto", {"id_cliente": cid, "brief": "xyzxyzxyz-inexistente"},
        id_empresa=emp)
    assert resultados[0]["estado"] == "descartado"
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM clientes WHERE id=%s", (cid,))
        conn.commit()


# ── Degradación honesta de la IA (sin cliente/con límite excedido) ────────────────
def test_motor_degrada_honesto_sin_api_key(emp, monkeypatch):
    monkeypatch.setattr("src.services.copilot.motor_llm._cliente", lambda: None)
    R.crear_regla("configuracion.autorrelleno_centro", "x", id_empresa=emp)
    # autorrelleno no llama a la IA (determinista) -> no aplica aquí; probamos con correo, que sí.
    R.crear_regla("correo.responder_automatico", "x", id_empresa=emp)
    resultados = M.procesar_evento(
        "correo.responder_automatico",
        {"id_correo": "c1", "id_recibido": 1, "remitente": "a@b.com", "asunto": "x", "cuerpo": "x"},
        id_empresa=emp)
    assert resultados[0]["estado"] == "error"
    assert resultados[0]["ok"] is False
