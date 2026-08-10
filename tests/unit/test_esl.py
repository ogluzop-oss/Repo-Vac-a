"""
Tests de ESL — Etiquetas electrónicas de precio dinámico (migración 0168, Fase 1).

Cubre: vinculación etiqueta↔artículo, detección de PENDIENTES, push MANUAL en modo simulado (no automático),
re-pendiente al cambiar el precio, respeto de la promoción como precio efectivo, aislamiento por
empresa+tienda, credencial del proveedor CIFRADA (nunca en claro) y localización (blink) degradable.
"""

import pytest

from src.services.esl import ESLGateway, config, registro, sync

TIENDA = "TIENDA_TEST_ESL"


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _vincular(fab, emp, cod, label, tienda=TIENDA, **kw):
    r = registro.vincular(cod, label, id_empresa=emp, id_tienda=tienda, **kw)
    fab._borrar("esl_labels", "label_id", label)
    return r


def test_vincular_y_pendiente(fab, emp):
    cod = fab.articulo(nombre="Leche", id_empresa=emp, precio=1.0)
    assert _vincular(fab, emp, cod, "LBL-1")
    # artículo inexistente no se puede vincular
    assert registro.vincular("NO_EXISTE", "LBL-X", id_empresa=emp, id_tienda=TIENDA) is None
    # recién vinculada → pendiente (nunca sincronizada)
    pend = sync.pendientes(id_empresa=emp, id_tienda=TIENDA)
    fila = [p for p in pend if p["label_id"] == "LBL-1"]
    assert fila and abs(float(fila[0]["precio_actual"]) - 1.0) < 1e-4


def test_sincronizar_manual_simulado(fab, emp):
    cod = fab.articulo(nombre="Pan", id_empresa=emp, precio=2.5)
    _vincular(fab, emp, cod, "LBL-2")
    # el push NO es automático: sigue pendiente hasta llamar a sincronizar()
    assert any(p["label_id"] == "LBL-2" for p in sync.pendientes(id_empresa=emp, id_tienda=TIENDA))
    r = sync.sincronizar(id_empresa=emp, id_tienda=TIENDA)
    assert r["ok"] >= 1 and r["error"] == 0
    # tras sincronizar deja de estar pendiente y queda ACTUALIZADA con el precio empujado
    assert not any(p["label_id"] == "LBL-2" for p in sync.pendientes(id_empresa=emp, id_tienda=TIENDA))
    lab = [l for l in registro.listar(id_empresa=emp, id_tienda=TIENDA) if l["label_id"] == "LBL-2"][0]
    assert lab["estado"] == "ACTUALIZADA" and abs(float(lab["precio_sincronizado"]) - 2.5) < 1e-4


def test_re_pendiente_tras_cambio_precio(fab, emp, db):
    cod = fab.articulo(nombre="Queso", id_empresa=emp, precio=4.0)
    _vincular(fab, emp, cod, "LBL-3")
    sync.sincronizar(id_empresa=emp, id_tienda=TIENDA)
    assert not any(p["label_id"] == "LBL-3" for p in sync.pendientes(id_empresa=emp, id_tienda=TIENDA))
    # cambia el precio → vuelve a pendiente con el nuevo precio efectivo
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("UPDATE articulos SET precio=4.75 WHERE codigo=%s", (cod,))
    pend = [p for p in sync.pendientes(id_empresa=emp, id_tienda=TIENDA) if p["label_id"] == "LBL-3"]
    assert pend and abs(float(pend[0]["precio_actual"]) - 4.75) < 1e-4
    sync.sincronizar(id_empresa=emp, id_tienda=TIENDA)
    lab = [l for l in registro.listar(id_empresa=emp, id_tienda=TIENDA) if l["label_id"] == "LBL-3"][0]
    assert abs(float(lab["precio_sincronizado"]) - 4.75) < 1e-4


def test_precio_efectivo_respeta_promo(fab, emp, db):
    cod = fab.articulo(nombre="Aceite", id_empresa=emp, precio=8.0)
    # activa una promo directamente sobre el artículo (si el esquema la soporta); si no, degrada al P.V.P.
    try:
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE articulos SET precio_promo=6.0, promo_activa=1 WHERE codigo=%s", (cod,))
        tiene_promo = True
    except Exception:
        tiene_promo = False
    pe = sync.precio_efectivo(cod, emp)
    assert abs(pe - (6.0 if tiene_promo else 8.0)) < 1e-4


def test_aislamiento_empresa_tienda(fab, emp):
    otra = fab.empresa("EMPRESA ESL B")
    cod_a = fab.articulo(nombre="Art A", id_empresa=emp, precio=1.0)
    cod_b = fab.articulo(nombre="Art B", id_empresa=otra, precio=1.0)
    _vincular(fab, emp, cod_a, "LBL-A", tienda=TIENDA)
    _vincular(fab, otra, cod_b, "LBL-B", tienda=TIENDA)
    labels_a = {l["label_id"] for l in registro.listar(id_empresa=emp, id_tienda=TIENDA)}
    labels_b = {l["label_id"] for l in registro.listar(id_empresa=otra, id_tienda=TIENDA)}
    assert "LBL-A" in labels_a and "LBL-A" not in labels_b
    assert "LBL-B" in labels_b and "LBL-B" not in labels_a
    # otra tienda de la misma empresa no ve la etiqueta
    assert not registro.listar(id_empresa=emp, id_tienda="OTRA_TIENDA")


def test_config_credencial_cifrada(fab, emp, db):
    fab._borrar("esl_config", "id_empresa", emp)
    assert config.guardar_config(proveedor="rest_generico", endpoint="https://api.demo/v1",
                                 store_id="S1", credencial="TOKEN_SECRETO_123", modo_simulado=False,
                                 id_empresa=emp, id_tienda=TIENDA)
    # en la BD la credencial NUNCA está en claro
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT credencial_cifrada FROM esl_config WHERE id_empresa=%s AND id_tienda=%s",
                    (emp, TIENDA))
        raw = cur.fetchone()[0]
    assert raw and "TOKEN_SECRETO_123" not in str(raw)
    # round-trip interno (uso del gateway) sí la recupera
    cfg = config.obtener_config(id_empresa=emp, id_tienda=TIENDA, incluir_credencial=True)
    assert cfg["_credencial"] == "TOKEN_SECRETO_123"
    # la vista pública no expone la credencial
    pub = config.obtener_config(id_empresa=emp, id_tienda=TIENDA)
    assert "credencial_cifrada" not in pub and "_credencial" not in pub and pub["tiene_credencial"] is True


def test_gateway_degradable_y_localizar(fab, emp):
    # sin endpoint → simulado aunque se pida modo real
    gw = ESLGateway(proveedor="rest_generico", endpoint=None, modo_simulado=False)
    assert gw.modo_simulado is True
    assert gw.push("L1", {"precio": 1})["ok"] and gw.localizar("L1")["ok"]
    # localizar a través del servicio (sin config → gateway simulado) no rompe
    cod = fab.articulo(nombre="Sardinas", id_empresa=emp, precio=1.0)
    _vincular(fab, emp, cod, "LBL-LOC")
    assert sync.localizar("LBL-LOC", id_empresa=emp, id_tienda=TIENDA).get("ok")
