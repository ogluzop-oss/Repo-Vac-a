"""
Motor de Alta Conversión e-Commerce · Carrito del storefront público (Drawer Cart): incremental,
identificado por `token_sesion`, siempre releyendo precio/disponibilidad del catálogo — nunca
confía en datos del cliente. `resumen()` debe reflejar promociones/cupón/envío reales (vía
`comercial.cotizar`, nunca recalculado a mano en el carrito)."""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.services.comercio_digital import carrito_storefront as C


@pytest.fixture
def emp(fab):
    return fab.empresa("CARRITO STOREFRONT TEST")


def _token():
    return "tok-" + uuid.uuid4().hex


def _producto_visible(fab, db, emp, *, precio=10.0, stock=20):
    cod = fab.articulo(id_empresa=emp, precio=precio, stock_total=stock, nombre="Carrito Test")
    pid = fab.producto_catalogo(cod, id_empresa=emp, titulo_web="Carrito Test Web", visible_web=1)
    return cod, pid


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("cd_carrito_lineas", "cd_carrito_actividad", "cd_carrito_abandono"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_anadir_producto_disponible(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp)
    r = C.anadir(_token(), emp, codigo=cod, cantidad=2)
    assert r == {"ok": True}


def test_anadir_por_id_producto_resuelve_el_codigo_real(fab, db, emp):
    """La ficha pública nunca expone `codigo_articulo` del producto base — el "Añadir al carrito"
    de la ficha de producto usa `id_producto` (el único identificador público del producto base),
    y el carrito debe resolver el `codigo_articulo` real por su cuenta, server-side."""
    cod, pid = _producto_visible(fab, db, emp)
    token = _token()
    r = C.anadir(token, emp, id_producto=pid, cantidad=2)
    assert r == {"ok": True}
    lineas = C.listar(token)
    assert len(lineas) == 1 and lineas[0]["codigo"] == cod and int(lineas[0]["cantidad"]) == 2


def test_anadir_sin_id_producto_ni_codigo_falla_honesto(db, emp):
    r = C.anadir(_token(), emp, cantidad=1)
    assert r == {"ok": False, "error": "falta_identificador_de_producto"}


def test_anadir_producto_inexistente_falla_honesto(db, emp):
    r = C.anadir(_token(), emp, codigo="NO-EXISTE-XYZ", cantidad=1)
    assert r["ok"] is False and r["error"] == "producto_no_disponible"


def test_anadir_mismo_codigo_dos_veces_incrementa_cantidad_no_duplica_linea(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=2)
    C.anadir(token, emp, codigo=cod, cantidad=3)
    lineas = C.listar(token)
    assert len(lineas) == 1
    assert int(lineas[0]["cantidad"]) == 5


def test_actualizar_cantidad_a_cero_quita_la_linea(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=1)
    id_linea = C.listar(token)[0]["id"]
    r = C.actualizar_cantidad(token, id_linea, 0)
    assert r["ok"] is True
    assert C.listar(token) == []


def test_quitar_linea(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=1)
    id_linea = C.listar(token)[0]["id"]
    assert C.quitar_linea(token, id_linea) is True
    assert C.listar(token) == []


def test_vaciar(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=1)
    assert C.vaciar(token) is True
    assert C.listar(token) == []


def test_capturar_email_honesto_sin_arroba_no_se_guarda(fab, db, emp):
    token = _token()
    assert C.capturar_email(token, emp, "no-es-un-email") is False
    assert C.email_de(token) is None
    assert C.capturar_email(token, emp, "cliente@test.com") is True
    assert C.email_de(token) == "cliente@test.com"


def test_resumen_carrito_vacio(db, emp):
    r = C.resumen(_token(), emp)
    assert r["lineas"] == [] and r["total"] == 0.0 and r["n_articulos"] == 0


def test_resumen_calcula_subtotal_y_total_vía_cotizar(fab, db, emp):
    cod, _pid = _producto_visible(fab, db, emp, precio=15.0)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=3)
    r = C.resumen(token, emp)
    assert r["n_articulos"] == 3
    assert r["subtotal"] == 45.0
    assert r["total"] == 45.0
    assert len(r["lineas"]) == 1 and r["lineas"][0]["cantidad"] == 3


def test_resumen_incluye_datos_de_envio_gratis_para_la_barra_de_progreso(fab, db, emp):
    from src.services.comercio_digital.envios import zonas
    zonas.crear_zona("España", paises="ES", tarifa_base=5.0, envio_gratis_desde=50.0, id_empresa=emp)
    cod, _pid = _producto_visible(fab, db, emp, precio=20.0)
    token = _token()
    C.anadir(token, emp, codigo=cod, cantidad=1)
    r = C.resumen(token, emp, pais_destino="ES")
    assert r["envio"]["umbral_envio_gratis"] == 50.0
    assert r["envio"]["falta_para_envio_gratis"] == 30.0
    assert r["envio"]["gratis"] is False
