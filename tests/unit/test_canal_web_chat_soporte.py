"""
Fase 6 e-commerce (Catálogo Web / Canal Web) — chat de soporte del storefront: IA primero
(degradable y honesta), escalado a un ticket SAT real cuando el visitante pide hablar con una
persona o la IA no puede ayudar, y de ahí en adelante la conversación vive ENTERAMENTE en
`ticket_comentarios` (nunca dos fuentes de verdad)."""

import pytest

pytestmark = pytest.mark.db

EMP = "T-CW-F6-CHAT"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cd_chat_mensajes WHERE token IN "
                       "(SELECT token FROM cd_chat_visitantes WHERE id_empresa=%s)", (EMP,))
            cur.execute("DELETE FROM cd_chat_visitantes WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM ticket_comentarios WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM tickets WHERE id_empresa=%s", (EMP,))
            conn.commit()
    _b()
    yield
    _b()


def test_mensaje_vacio_se_rechaza(limpia):
    from src.services.comercio_digital.canal_web import soporte_chat
    r = soporte_chat.enviar_mensaje(EMP, None, "   ")
    assert r == {"error": "texto_vacio"}


def test_sin_ia_configurada_escala_automaticamente_a_un_ticket(limpia, monkeypatch):
    """Degradación honesta (sin API key): el visitante NUNCA se queda sin respuesta — se deriva
    a un ticket SAT real en vez de un error mudo."""
    import src.services.comercio_digital.canal_web.soporte_chat as mod
    monkeypatch.setattr(mod, "_responder_ia", lambda *a, **k: None)
    r = mod.enviar_mensaje(EMP, None, "¿Tenéis la talla M en azul?")
    assert r["escalado"] is True
    assert r["id_ticket"]
    assert any("agente humano" in m["texto"].lower() for m in r["mensajes"])

    from src.services.sat import tickets as _tk
    t = _tk.obtener(r["id_ticket"])
    assert t["canal"] == "chat_web"


def test_peticion_explicita_de_humano_escala_sin_llamar_a_la_ia(limpia, monkeypatch):
    import src.services.comercio_digital.canal_web.soporte_chat as mod
    llamadas = []
    monkeypatch.setattr(mod, "_responder_ia", lambda *a, **k: llamadas.append(1) or "no debería usarse")
    r = mod.enviar_mensaje(EMP, None, "Quiero hablar con una persona, por favor")
    assert r["escalado"] is True
    assert llamadas == []   # la IA ni se invoca si el visitante pide humano explícitamente


def test_marcador_de_escalado_de_la_ia_tambien_escala(limpia, monkeypatch):
    import src.services.comercio_digital.canal_web.soporte_chat as mod
    monkeypatch.setattr(mod, "_responder_ia", lambda *a, **k: "ESCALAR_HUMANO")
    r = mod.enviar_mensaje(EMP, None, "Algo muy raro que la IA no entiende")
    assert r["escalado"] is True
    assert r["id_ticket"]


def test_respuesta_normal_de_la_ia_no_escala_y_persiste_el_turno(limpia, monkeypatch):
    import src.services.comercio_digital.canal_web.soporte_chat as mod
    monkeypatch.setattr(mod, "_responder_ia", lambda *a, **k: "Claro, el horario de atención es de 9 a 18h.")
    r = mod.enviar_mensaje(EMP, None, "¿Cuál es el horario?")
    assert r["escalado"] is False
    assert r["id_ticket"] is None
    textos = [m["texto"] for m in r["mensajes"]]
    assert "¿Cuál es el horario?" in textos
    assert "Claro, el horario de atención es de 9 a 18h." in textos


def test_segundo_mensaje_tras_escalar_va_a_ticket_comentarios(limpia, monkeypatch):
    import src.services.comercio_digital.canal_web.soporte_chat as mod
    monkeypatch.setattr(mod, "_responder_ia", lambda *a, **k: None)
    r1 = mod.enviar_mensaje(EMP, None, "Necesito ayuda urgente")
    token = r1["token"]
    r2 = mod.enviar_mensaje(EMP, token, "¿Alguien me puede atender ya?")
    assert r2["escalado"] is True
    assert r2["id_ticket"] == r1["id_ticket"]

    from src.services.sat import tickets as _tk
    comentarios = _tk.listar_comentarios(r2["id_ticket"], id_empresa=EMP)
    assert any(c["cuerpo"] == "¿Alguien me puede atender ya?" and c["es_cliente"] for c in comentarios)


def test_notas_internas_del_agente_no_se_muestran_al_visitante(limpia, monkeypatch):
    import src.services.comercio_digital.canal_web.soporte_chat as mod
    from src.services.sat import tickets as _tk
    monkeypatch.setattr(mod, "_responder_ia", lambda *a, **k: None)
    r = mod.enviar_mensaje(EMP, None, "Mi pedido no ha llegado")
    _tk.comentar(r["id_ticket"], "Nota interna: revisar con el transportista", interno=True, id_empresa=EMP)
    _tk.comentar(r["id_ticket"], "Ya estamos en ello, disculpa la demora", es_cliente=False, id_empresa=EMP)

    hilo = mod.obtener_hilo(EMP, r["token"])
    textos = [m["texto"] for m in hilo["mensajes"]]
    assert "Ya estamos en ello, disculpa la demora" in textos
    assert not any("Nota interna" in t for t in textos)


def test_obtener_hilo_token_desconocido_devuelve_vacio_sin_lanzar(limpia):
    from src.services.comercio_digital.canal_web import soporte_chat
    r = soporte_chat.obtener_hilo(EMP, "token-que-no-existe")
    assert r == {"token": None, "mensajes": [], "escalado": False, "id_ticket": None}


# ── Flask: endpoints del storefront ──────────────────────────────────────────

def test_endpoint_post_mensaje_y_get_hilo(db, fab, monkeypatch):
    from src.backend.app import crear_app
    import src.services.comercio_digital.canal_web.soporte_chat as mod
    monkeypatch.setattr(mod, "_responder_ia", lambda *a, **k: "Respuesta automática de prueba.")
    fab.web(activa=1, nombre="Tienda Chat Test")
    cli = crear_app().test_client()

    r1 = cli.post(f"/tienda/{fab.EMP_DEFECTO}/soporte/mensaje", json={"texto": "Hola"})
    assert r1.status_code == 200
    d1 = r1.get_json()
    assert d1["token"]
    assert any(m["texto"] == "Respuesta automática de prueba." for m in d1["mensajes"])

    r2 = cli.get(f"/tienda/{fab.EMP_DEFECTO}/soporte/hilo?token={d1['token']}")
    assert r2.status_code == 200
    assert r2.get_json()["mensajes"]


def test_endpoint_texto_vacio_devuelve_400(db, fab):
    from src.backend.app import crear_app
    fab.web(activa=1, nombre="Tienda Chat Test 2")
    cli = crear_app().test_client()
    r = cli.post(f"/tienda/{fab.EMP_DEFECTO}/soporte/mensaje", json={"texto": ""})
    assert r.status_code == 400


def test_widget_de_chat_aparece_en_la_home_de_una_tienda_activa(db, fab):
    from src.backend import storefront as sf
    fab.web(activa=1, nombre="Tienda Con Widget")
    html = sf.pagina_home(fab.EMP_DEFECTO)
    assert "smchat" in html


def test_widget_de_chat_no_aparece_en_tienda_no_disponible(db, fab):
    from src.backend import storefront as sf
    fab.web(activa=0, nombre="Tienda Sin Widget")
    html = sf._no_disponible(sf.web_tienda.obtener_config(fab.EMP_DEFECTO), fab.EMP_DEFECTO)
    assert "smchat" not in html
