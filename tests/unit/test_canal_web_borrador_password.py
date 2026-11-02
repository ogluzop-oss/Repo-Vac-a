"""
Fase 5 e-commerce (Catálogo Web / Canal Web) — borrador con contraseña:
`canal_web.configurar_borrador` (hash vía `seguridad.passwords`, único editor de `web_config`) y
el gate HTTP Basic en `backend/storefront.py` (cero regresión: sin borrador, la tienda responde
exactamente igual que siempre)."""

import pytest

pytestmark = pytest.mark.db

EMP = "T-CW-F5-BORRADOR"
GER = {"perfil": "ADMINISTRADOR", "id": "g5"}


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM web_config WHERE id_empresa=%s", (EMP,))
            conn.commit()
    _b()
    yield
    _b()


# ── servicio: canal_web.configurar_borrador ──────────────────────────────────

def test_activar_borrador_sin_password_falla_honesto(limpia):
    from src.services.comercio_digital import canal_web
    r = canal_web.configurar_borrador(activar=True, password="", id_empresa=EMP, usuario=GER)
    assert r == {"ok": False, "error": "password_requerida"}


def test_activar_borrador_respeta_rbac(limpia):
    from src.services.comercio_digital import canal_web
    r = canal_web.configurar_borrador(activar=True, password="secreta123",
                                      id_empresa=EMP, usuario={"perfil": "SIN", "id": "x"})
    assert r.get("error") == "forbidden"


def test_activar_borrador_hashea_y_nunca_guarda_texto_plano(limpia):
    from src.db import web_tienda
    from src.services.comercio_digital import canal_web
    r = canal_web.configurar_borrador(activar=True, password="secreta123", id_empresa=EMP, usuario=GER)
    assert r == {"ok": True, "borrador": True}
    cfg = web_tienda.obtener_config(EMP)
    assert int(cfg["borrador"]) == 1
    assert cfg["password_hash"] and cfg["password_hash"] != "secreta123"


def test_desactivar_borrador_borra_el_hash(limpia):
    from src.db import web_tienda
    from src.services.comercio_digital import canal_web
    canal_web.configurar_borrador(activar=True, password="secreta123", id_empresa=EMP, usuario=GER)
    r = canal_web.configurar_borrador(activar=False, id_empresa=EMP, usuario=GER)
    assert r == {"ok": True, "borrador": False}
    cfg = web_tienda.obtener_config(EMP)
    assert int(cfg["borrador"]) == 0 and cfg["password_hash"] == ""


# ── storefront: gate HTTP Basic ───────────────────────────────────────────────

def test_tienda_sin_borrador_responde_igual_que_siempre(db, fab):
    from src.backend.app import crear_app
    fab.web(activa=1, nombre="Tienda Publica")
    cli = crear_app().test_client()
    r = cli.get(f"/tienda/{fab.EMP_DEFECTO}")
    assert r.status_code == 200


def test_tienda_en_borrador_exige_contrasena(db, fab):
    from src.backend.app import crear_app
    from src.services.comercio_digital import canal_web
    fab.web(activa=1, nombre="Tienda Borrador")
    canal_web.configurar_borrador(activar=True, password="miclave", id_empresa=fab.EMP_DEFECTO,
                                  usuario=GER)
    cli = crear_app().test_client()
    sin_cred = cli.get(f"/tienda/{fab.EMP_DEFECTO}")
    assert sin_cred.status_code == 401
    assert "WWW-Authenticate" in sin_cred.headers

    import base64
    malas = base64.b64encode(b"x:incorrecta").decode()
    con_cred_mala = cli.get(f"/tienda/{fab.EMP_DEFECTO}", headers={"Authorization": f"Basic {malas}"})
    assert con_cred_mala.status_code == 401

    buenas = base64.b64encode(b"x:miclave").decode()
    con_cred_buena = cli.get(f"/tienda/{fab.EMP_DEFECTO}", headers={"Authorization": f"Basic {buenas}"})
    assert con_cred_buena.status_code == 200
    canal_web.configurar_borrador(activar=False, id_empresa=fab.EMP_DEFECTO, usuario=GER)


def test_tienda_inactiva_en_borrador_sigue_dando_404_no_401(db, fab):
    """`activa=0` manda siempre — el gate de contraseña solo aplica a una tienda que por lo demás
    respondería (nunca abre una rendija de "¿existe o no?" en una tienda despublicada)."""
    from src.backend.app import crear_app
    from src.services.comercio_digital import canal_web
    fab.web(activa=0, nombre="Tienda Inactiva")
    canal_web.configurar_borrador(activar=True, password="miclave", id_empresa=fab.EMP_DEFECTO,
                                  usuario=GER)
    cli = crear_app().test_client()
    r = cli.get(f"/tienda/{fab.EMP_DEFECTO}")
    assert r.status_code == 404
    canal_web.configurar_borrador(activar=False, id_empresa=fab.EMP_DEFECTO, usuario=GER)
