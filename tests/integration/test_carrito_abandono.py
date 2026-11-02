"""
Motor de Recuperación de Carritos Abandonados (storefront público) · detección por inactividad +
email capturado, recuperación por correo reutilizando la infraestructura SMTP existente."""

import datetime as _dt
import uuid

import pytest

pytestmark = pytest.mark.db

from src.services.comercio_digital import carrito_abandono as AB
from src.services.comercio_digital import carrito_storefront as C


@pytest.fixture
def emp(fab):
    return fab.empresa("CARRITO ABANDONO TEST")


def _token():
    return "tok-ab-" + uuid.uuid4().hex


def _producto_visible(fab, db, emp, *, precio=10.0, stock=20):
    cod = fab.articulo(id_empresa=emp, precio=precio, stock_total=stock, nombre="Abandono Test")
    pid = fab.producto_catalogo(cod, id_empresa=emp, titulo_web="Abandono Test Web", visible_web=1)
    return cod, pid


def _forzar_inactividad(db, token_sesion, minutos_atras):
    """Simula que el carrito lleva tiempo sin tocarse — retrasa `creado_en`/`actualizado_en` para
    no depender de dormir de verdad en el test."""
    hace = _dt.datetime.now() - _dt.timedelta(minutes=minutos_atras)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE cd_carrito_lineas SET creado_en=%s WHERE token_sesion=%s", (hace, token_sesion))
        cur.execute("UPDATE cd_carrito_actividad SET actualizado_en=%s WHERE token_sesion=%s",
                    (hace, token_sesion))
        conn.commit()


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("cd_carrito_lineas", "cd_carrito_actividad", "cd_carrito_abandono"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_carrito_reciente_no_es_candidato(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=1)
    nuevos = AB.detectar_y_marcar(minutos_umbral=30)
    assert not any(c["token_sesion"] == token for c in nuevos)


def test_carrito_inactivo_se_marca_como_abandonado(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=2)
    _forzar_inactividad(db, token, 45)
    nuevos = AB.detectar_y_marcar(minutos_umbral=30)
    assert any(c["token_sesion"] == token for c in nuevos)
    reg = AB.obtener(token)
    assert reg is not None and reg["n_lineas"] == 1 and reg["resuelto"] == 0


def test_no_se_remarca_sin_cambios_en_pasadas_sucesivas(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=1)
    _forzar_inactividad(db, token, 45)
    primeros = AB.detectar_y_marcar(minutos_umbral=30)
    assert any(c["token_sesion"] == token for c in primeros)
    segundos = AB.detectar_y_marcar(minutos_umbral=30)
    assert not any(c["token_sesion"] == token for c in segundos)   # idempotente, no re-marcado


def test_vaciar_carrito_resuelve_el_abandono(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=1)
    _forzar_inactividad(db, token, 45)
    AB.detectar_y_marcar(minutos_umbral=30)
    assert AB.obtener(token)["resuelto"] == 0
    C.vaciar(token)
    assert AB.obtener(token)["resuelto"] == 1


def test_listar_para_empresa_solo_sin_resolver(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=1)
    _forzar_inactividad(db, token, 45)
    AB.detectar_y_marcar(minutos_umbral=30)
    assert any(c["token_sesion"] == token for c in AB.listar_para_empresa(emp))
    AB.marcar_resuelto(token)
    assert not any(c["token_sesion"] == token for c in AB.listar_para_empresa(emp))


def test_recuperacion_sin_email_capturado_degrada_honesto(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=1)
    _forzar_inactividad(db, token, 45)
    AB.detectar_y_marcar(minutos_umbral=30)
    r = AB.enviar_recuperacion(token)
    assert r == {"ok": False, "motivo": "sin_email_capturado"}


def test_recuperacion_con_email_pero_sin_buzon_activo_degrada_honesto(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=1)
    C.capturar_email(token, emp, "comprador@test.com")
    _forzar_inactividad(db, token, 45)
    AB.detectar_y_marcar(minutos_umbral=30)
    r = AB.enviar_recuperacion(token)
    # Empresa de test recién creada: sin buzón corporativo configurado -> degrada, nunca lanza.
    assert r["ok"] is False and r["motivo"] == "sin_buzon_activo"


def test_recuperacion_envia_y_marca_notificado_una_sola_vez(fab, db, emp, monkeypatch):
    cod, _pid = _producto_visible(fab, db, emp)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=1)
    C.capturar_email(token, emp, "comprador@test.com")
    _forzar_inactividad(db, token, 45)
    AB.detectar_y_marcar(minutos_umbral=30)

    monkeypatch.setattr(
        "src.db.correo.listar_correos",
        lambda eid: [{"id_correo": "buzon-fake", "estado": "activo"}])
    enviados = []
    monkeypatch.setattr(
        "src.services.correo.servicio.enviar_documento",
        lambda id_correo, dest, asunto, cuerpo="", adjuntos=None:
            (enviados.append((dest, asunto)) or (True, "ok")))

    r1 = AB.enviar_recuperacion(token, base_url="http://localhost:8090")
    assert r1["ok"] is True
    assert len(enviados) == 1
    assert enviados[0][0] == "comprador@test.com"

    # Segunda llamada: ya notificado -> no reenvía (degrada, "no_aplica").
    r2 = AB.enviar_recuperacion(token)
    assert r2 == {"ok": False, "motivo": "no_aplica"}
    assert len(enviados) == 1
