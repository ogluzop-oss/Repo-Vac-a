"""
Suscripción de la delegación a SOMA al Event Bus (`services.soma_delegacion.wiring`) — un evento
de negocio real (`CORREO_RECIBIDO`, `CENTRO_CREADO`) dispara la evaluación de las reglas activas
sin que el llamador original (`db.correo.guardar_recibido`, `db.centros.crear_centro`) sepa nada
de la delegación. También cubre el bug cerrado en esta misma entrega: antes `CORREO_RECIBIDO` se
republicaba en cada resincronización para correos YA vistos — eso habría disparado una respuesta
automática repetida al mismo correo en cada ciclo del latido de 2 min.
"""

import pytest

from src.services import eventos as EV
from src.services.soma_delegacion import historial as H
from src.services.soma_delegacion import reglas as R
from src.services.soma_delegacion import wiring

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
        cur.execute("DELETE FROM correos_recibidos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM correos_corporativos WHERE id_empresa=%s", (emp,))
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


def test_correo_recibido_se_publica_solo_una_vez_por_mensaje(emp):
    """Cierre del bug: re-guardar el MISMO message_id (como hace una resincronización que
    reprocesa los últimos N correos) no debe volver a publicar CORREO_RECIBIDO."""
    from src.db import correo as correo_db

    vistos = []
    handler = lambda ev: vistos.append(ev)
    EV.suscribir("CORREO_RECIBIDO", handler)
    try:
        correo_db.guardar_recibido("buzon-x", "a@test.com", "asunto", "cuerpo",
                                   message_id="<dup-1@test>", id_empresa=emp)
        correo_db.guardar_recibido("buzon-x", "a@test.com", "asunto", "cuerpo",
                                   message_id="<dup-1@test>", id_empresa=emp)   # resincronización
        correo_db.guardar_recibido("buzon-x", "a@test.com", "asunto", "cuerpo",
                                   message_id="<dup-1@test>", id_empresa=emp)   # otra más
        assert len(vistos) == 1
    finally:
        EV.desuscribir("CORREO_RECIBIDO", handler)


def test_wiring_dispara_respuesta_automatica_al_recibir_correo_nuevo(fab, emp, monkeypatch, db):
    wiring.registrar_suscripciones()
    id_correo = fab.buzon_correo(id_empresa=emp)
    R.crear_regla("correo.responder_automatico", "Responde a preguntas de horario.",
                  modo_aplicacion="revisar_antes", id_empresa=emp)
    _mock_ia_json(monkeypatch,
                  '{"aplica": true, "motivo": "pregunta de horario", "respuesta": "De 9 a 18h."}')

    from src.db import correo as correo_db
    correo_db.guardar_recibido(id_correo, "cliente@test.com", "Horario", "¿A qué hora abrís?",
                               message_id="<wire-1@test>", id_empresa=emp)

    hist = H.listar(id_empresa=emp, tipo="correo.responder_automatico")
    assert len(hist) == 1 and hist[0]["estado"] == "pendiente_revision"

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM correos_recibidos WHERE id_correo=%s", (id_correo,))
        conn.commit()


def test_wiring_no_dispara_nada_sin_regla_activa(fab, emp, db):
    wiring.registrar_suscripciones()
    id_correo = fab.buzon_correo(id_empresa=emp)
    from src.db import correo as correo_db
    correo_db.guardar_recibido(id_correo, "cliente@test.com", "Cualquier cosa", "cuerpo",
                               message_id="<wire-2@test>", id_empresa=emp)
    assert H.listar(id_empresa=emp, tipo="correo.responder_automatico") == []
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM correos_recibidos WHERE id_correo=%s", (id_correo,))
        conn.commit()


def test_centro_creado_publica_evento_con_el_id_del_centro(emp):
    from src.db import centros as centros_db

    vistos = []
    handler = lambda ev: vistos.append(ev)
    EV.suscribir("CENTRO_CREADO", handler)
    try:
        id_centro = centros_db.crear_centro(id_empresa=emp, nombre_centro="Centro Evento Test")
        assert any(ev.get("ref_id") == id_centro for ev in vistos)
    finally:
        EV.desuscribir("CENTRO_CREADO", handler)


def test_wiring_autorrellena_centro_nuevo_automaticamente(emp):
    wiring.registrar_suscripciones()
    from src.db import centros as centros_db
    from src.db import empresa as empresa_db
    empresa_db.actualizar_empresa(emp, telefono="900555666", email_principal="hola@test.com")
    R.crear_regla("configuracion.autorrelleno_centro", "Rellena datos de contacto.",
                  id_empresa=emp)

    id_centro = centros_db.crear_centro(id_empresa=emp, nombre_centro="Centro Autorrelleno Wiring")
    centro = centros_db.obtener_centro(id_centro)
    assert centro["telefono"] == "900555666"
    assert centro["email"] == "hola@test.com"


def test_wiring_dispara_autorrelleno_proveedor_al_crearlo(emp, monkeypatch, db):
    wiring.registrar_suscripciones()
    from src.db import proveedores as prov_db
    R.crear_regla("configuracion.autorrelleno_proveedor", "Proveedores nacionales a 60 días.",
                  id_empresa=emp)
    _mock_ia_json(monkeypatch, '{"plazo_pago": 60, "divisa": "EUR"}')

    pid = prov_db.crear_proveedor("Proveedor Wiring", id_empresa=emp)
    hist = H.listar(id_empresa=emp, tipo="configuracion.autorrelleno_proveedor")
    assert len(hist) == 1 and hist[0]["estado"] == "aplicado"
    proveedor = prov_db.obtener_proveedor(pid, id_empresa=emp)
    assert int(proveedor["plazo_pago"]) == 60

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM proveedores WHERE id_proveedor=%s", (pid,))
        conn.commit()


def test_wiring_dispara_respuesta_automatica_ticket_al_crearlo(emp, monkeypatch, db):
    wiring.registrar_suscripciones()
    from src.services.sat import tickets
    R.crear_regla("sat.responder_ticket", "Responde preguntas de devolución.",
                  modo_aplicacion="automatico", id_empresa=emp)
    _mock_ia_json(monkeypatch,
                  '{"aplica": true, "motivo": "devolución", "respuesta": "30 días para devolver."}')

    tid = tickets.crear_ticket("¿Puedo devolver un producto?", descripcion="Quiero devolverlo.",
                               id_empresa=emp)
    comentarios = tickets.listar_comentarios(tid, id_empresa=emp)
    assert len(comentarios) == 1 and comentarios[0]["autor"] == "SOMA"

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ticket_comentarios WHERE id_ticket=%s", (tid,))
        cur.execute("DELETE FROM tickets WHERE id=%s", (tid,))
        conn.commit()
