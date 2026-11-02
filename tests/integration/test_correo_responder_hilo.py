"""
Enhebrado real de respuestas de correo (`services.correo.servicio.responder_correo`) — cabeceras
In-Reply-To/References sobre el Message-ID original, para que el cliente del destinatario
(Gmail, Outlook…) agrupe la respuesta en el mismo hilo en vez de mostrarla como un correo suelto.
Usado por la automatización de respuesta automática de SOMA, pero es de uso general.
"""

import pytest

from src.db import correo as correo_db
from src.services.correo import servicio

pytestmark = pytest.mark.db


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM correos_recibidos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM correos_corporativos WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_construir_mime_incluye_cabeceras_de_hilo():
    msg = servicio._construir_mime("yo@test.com", "tu@test.com", "Re: Asunto", "cuerpo", None,
                                   in_reply_to="<original@test>", references="<original@test>")
    assert msg["In-Reply-To"] == "<original@test>"
    assert msg["References"] == "<original@test>"


def test_construir_mime_sin_in_reply_to_no_anade_cabeceras():
    msg = servicio._construir_mime("yo@test.com", "tu@test.com", "Asunto", "cuerpo", None)
    assert msg["In-Reply-To"] is None
    assert msg["References"] is None


def test_responder_correo_resuelve_destinatario_asunto_e_hilo(fab, emp):
    id_correo = fab.buzon_correo(id_empresa=emp)
    id_recibido = correo_db.guardar_recibido(
        id_correo, "Cliente Real <cliente@test.com>", "Consulta sobre el pedido", "cuerpo original",
        message_id="<orig-123@test>", id_empresa=emp)

    ok, msg = servicio.responder_correo(id_correo, id_recibido, "Aquí tienes la respuesta.",
                                        id_empresa=emp)
    assert ok, msg

    # Modo simulado: el .eml queda guardado en disco — se lee para comprobar el enhebrado real.
    import glob
    import os
    carpeta = os.path.join(servicio._dir_documentos(), "correo_enviados", emp)
    emls = sorted(glob.glob(os.path.join(carpeta, "*.eml")), key=os.path.getmtime)
    assert emls
    contenido = open(emls[-1], "rb").read().decode("utf-8", "ignore")
    assert "In-Reply-To: <orig-123@test>" in contenido
    assert "References: <orig-123@test>" in contenido
    assert "To: cliente@test.com" in contenido
    assert "Subject: Re: Consulta sobre el pedido" in contenido
    for f in emls:
        os.remove(f)


def test_responder_correo_no_duplica_prefijo_re(fab, emp):
    id_correo = fab.buzon_correo(id_empresa=emp)
    id_recibido = correo_db.guardar_recibido(
        id_correo, "x@test.com", "Re: Ya era una respuesta", "cuerpo",
        message_id="<orig-456@test>", id_empresa=emp)
    ok, _msg = servicio.responder_correo(id_correo, id_recibido, "ok", id_empresa=emp)
    assert ok
    import glob
    import os
    carpeta = os.path.join(servicio._dir_documentos(), "correo_enviados", emp)
    emls = sorted(glob.glob(os.path.join(carpeta, "*.eml")), key=os.path.getmtime)
    contenido = open(emls[-1], "rb").read().decode("utf-8", "ignore")
    assert "Subject: Re: Ya era una respuesta" in contenido
    assert "Re: Re:" not in contenido
    for f in emls:
        os.remove(f)


def test_responder_correo_original_inexistente_falla_honesto(fab, emp):
    id_correo = fab.buzon_correo(id_empresa=emp)
    ok, msg = servicio.responder_correo(id_correo, 999999999, "x", id_empresa=emp)
    assert ok is False


def test_responder_correo_de_otro_buzon_falla_honesto(fab, emp):
    id_correo_a = fab.buzon_correo(id_empresa=emp)
    id_correo_b = fab.buzon_correo(id_empresa=emp)
    id_recibido = correo_db.guardar_recibido(
        id_correo_a, "x@test.com", "asunto", "cuerpo", message_id="<orig-789@test>", id_empresa=emp)
    ok, msg = servicio.responder_correo(id_correo_b, id_recibido, "x", id_empresa=emp)
    assert ok is False
