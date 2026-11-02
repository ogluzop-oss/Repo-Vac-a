"""
Asistente de Vinculación RFID (`services.rfid.vinculacion` + los nuevos accesores de `db.ubicaciones`/
`db.articulos`): EAN → número de serie → EPC (SGTIN-96) → grabación física → lectura cruzada →
persistencia en `ubicaciones`. BD real (`*_test`), gateway FALSO controlable (simula hardware
conectado/desconectado/tag ausente) — nunca toca `src.utils.rfid_gateway` de verdad."""

import pytest

from src.db import articulos as art_db
from src.db import ubicaciones as ubi_db
from src.services.rfid import vinculacion as V
from src.utils.ean import digito_control

pytestmark = pytest.mark.db


class _GatewayFalso:
    """Gateway controlable: `ok_escritura`/`ok_lectura` deciden si `escribir_tag`/`leer_tag` tienen
    éxito; `epc_leido_distinto=True` simula una lectura cruzada que NO coincide con lo escrito."""

    def __init__(self, ok_escritura=True, ok_lectura=True, epc_leido_distinto=False):
        self.ok_escritura = ok_escritura
        self.ok_lectura = ok_lectura
        self.epc_leido_distinto = epc_leido_distinto
        self._ultimo = None

    def escribir_tag(self, epc):
        if not self.ok_escritura:
            return False
        self._ultimo = epc
        return True

    def leer_tag(self):
        if not self.ok_lectura:
            return None
        if self.epc_leido_distinto:
            return "EPC-QUE-NO-COINCIDE"
        return self._ultimo


def _ean(cuerpo_11_digitos):
    doce = f"20{cuerpo_11_digitos}"[:12].ljust(12, "0")
    return f"{doce}{digito_control(doce)}"


@pytest.fixture
def emp(fab):
    return fab.empresa("RFID VINCULACION TEST")


def _producto(fab, emp, sufijo, *, precio=12.0, stock=5):
    codigo = _ean(sufijo)
    fab.articulo(codigo=codigo, id_empresa=emp, precio=precio, stock_total=stock, nombre="Prod RFID")
    return codigo


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ubicaciones WHERE id_empresa=%s", (emp,))
        conn.commit()


# ── db.articulos.ficha_rfid ───────────────────────────────────────────────────
def test_ficha_rfid_devuelve_datos_compactos(fab, db, emp):
    codigo = _producto(fab, emp, "11111111111", precio=9.5, stock=7)
    ficha = art_db.ficha_rfid(codigo, id_empresa=emp)
    assert ficha["codigo"] == codigo
    assert ficha["precio"] == 9.5
    assert ficha["stock_total"] == 7


def test_ficha_rfid_articulo_inexistente_da_none(db, emp):
    assert art_db.ficha_rfid("0000000000000", id_empresa=emp) is None


# ── db.ubicaciones: serie + registro de etiqueta ──────────────────────────────
def test_siguiente_numero_serie_empieza_en_uno(fab, db, emp):
    codigo = _producto(fab, emp, "22222222222")
    assert ubi_db.siguiente_numero_serie(codigo) == 1


def test_siguiente_numero_serie_incrementa_tras_registrar(fab, db, emp):
    codigo = _producto(fab, emp, "33333333333")
    r1 = ubi_db.registrar_etiqueta_rfid("EPC-SERIE-1", codigo, 1, id_empresa=emp)
    assert r1["ok"] is True
    assert ubi_db.siguiente_numero_serie(codigo) == 2
    r2 = ubi_db.registrar_etiqueta_rfid("EPC-SERIE-2", codigo, 2, id_empresa=emp)
    assert r2["ok"] is True
    assert ubi_db.siguiente_numero_serie(codigo) == 3


def test_registrar_etiqueta_epc_duplicado_falla_honesto(fab, db, emp):
    codigo = _producto(fab, emp, "44444444444")
    assert ubi_db.registrar_etiqueta_rfid("EPC-DUP", codigo, 1, id_empresa=emp)["ok"] is True
    r = ubi_db.registrar_etiqueta_rfid("EPC-DUP", codigo, 2, id_empresa=emp)
    assert r["ok"] is False and r["error"] == "epc_ya_registrado"


def test_listar_y_contar_etiquetas_articulo(fab, db, emp):
    codigo = _producto(fab, emp, "55555555555")
    ubi_db.registrar_etiqueta_rfid("EPC-A", codigo, 1, id_empresa=emp)
    ubi_db.registrar_etiqueta_rfid("EPC-B", codigo, 2, id_empresa=emp)
    etiquetas = ubi_db.listar_etiquetas_articulo(codigo)
    assert len(etiquetas) == 2
    assert {e["epc"] for e in etiquetas} == {"EPC-A", "EPC-B"}
    assert ubi_db.contar_etiquetas_articulo(codigo) == 2


def test_obtener_por_epc(fab, db, emp):
    codigo = _producto(fab, emp, "66666666666")
    ubi_db.registrar_etiqueta_rfid("EPC-LOOKUP", codigo, 1, id_empresa=emp)
    fila = ubi_db.obtener_por_epc("EPC-LOOKUP")
    assert fila is not None and fila["codigo_articulo"] == codigo
    assert ubi_db.obtener_por_epc("EPC-NO-EXISTE") is None


# ── services.rfid.vinculacion: pipeline completo ──────────────────────────────
def test_buscar_articulo_por_codigo_exacto(fab, db, emp):
    codigo = _producto(fab, emp, "77777777777")
    assert V.buscar_articulo(codigo, id_empresa=emp)["codigo"] == codigo


def test_buscar_articulo_inexistente_da_none(db, emp):
    assert V.buscar_articulo("no existe esto", id_empresa=emp) is None


def test_preparar_serie_y_epc_autogenera_serial(fab, db, emp):
    codigo = _producto(fab, emp, "88888888888")
    datos = V.preparar_serie_y_epc(codigo)
    assert datos is not None
    assert datos["serial"] == 1
    assert len(datos["epc_hex"]) == 24


def test_vincular_articulo_exito_persiste_en_ubicaciones(fab, db, emp):
    codigo = _producto(fab, emp, "99999999999")
    gw = _GatewayFalso()
    r = V.vincular_articulo(gw, codigo, id_empresa=emp)
    assert r["ok"] is True
    assert r["numero_serie"] == 1
    fila = ubi_db.obtener_por_epc(r["epc_hex"])
    assert fila is not None and fila["codigo_articulo"] == codigo and fila["numero_serie"] == 1


def test_vincular_articulo_sin_gateway_falla_honesto(fab, db, emp):
    codigo = _producto(fab, emp, "10101010101")
    r = V.vincular_articulo(None, codigo, id_empresa=emp)
    assert r["ok"] is False and r["motivo"] == V.SIN_HARDWARE
    assert ubi_db.contar_etiquetas_articulo(codigo) == 0


def test_vincular_articulo_fallo_escritura_no_persiste(fab, db, emp):
    codigo = _producto(fab, emp, "12121212121")
    gw = _GatewayFalso(ok_escritura=False)
    r = V.vincular_articulo(gw, codigo, id_empresa=emp)
    assert r["ok"] is False and r["motivo"] == V.FALLO_ESCRITURA
    assert ubi_db.contar_etiquetas_articulo(codigo) == 0


def test_vincular_articulo_fallo_lectura_cruzada_no_persiste(fab, db, emp):
    codigo = _producto(fab, emp, "13131313131")
    gw = _GatewayFalso(epc_leido_distinto=True)
    r = V.vincular_articulo(gw, codigo, id_empresa=emp)
    assert r["ok"] is False and r["motivo"] == V.FALLO_VERIFICACION
    assert ubi_db.contar_etiquetas_articulo(codigo) == 0


def test_vincular_articulo_codigo_invalido_falla_honesto(db, emp):
    gw = _GatewayFalso()
    r = V.vincular_articulo(gw, "NO-ES-UN-GTIN", id_empresa=emp)
    assert r["ok"] is False and r["motivo"] == V.SIN_ARTICULO


def test_vincular_lote_varias_unidades_series_consecutivas(fab, db, emp):
    codigo = _producto(fab, emp, "14141414141")
    gw = _GatewayFalso()
    progreso = []
    res = V.vincular_lote(gw, [codigo], cantidad_por_articulo=3, id_empresa=emp,
                          on_progreso=lambda i, t, r: progreso.append((i, t, r["ok"])))
    assert res["total"] == 3 and res["ok"] == 3 and res["fallidos"] == []
    assert progreso == [(1, 3, True), (2, 3, True), (3, 3, True)]
    etiquetas = ubi_db.listar_etiquetas_articulo(codigo)
    assert sorted(e["numero_serie"] for e in etiquetas) == [1, 2, 3]


def test_vincular_lote_reporta_fallidos_sin_abortar_el_resto(fab, db, emp):
    codigo = _producto(fab, emp, "15151515151")
    gw = _GatewayFalso(ok_escritura=False)
    res = V.vincular_lote(gw, [codigo], cantidad_por_articulo=2, id_empresa=emp)
    assert res["total"] == 2 and res["ok"] == 0 and len(res["fallidos"]) == 2
