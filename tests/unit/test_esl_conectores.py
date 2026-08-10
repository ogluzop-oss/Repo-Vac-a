"""
Tests de los CONECTORES ESL reales (Fase 3) — adaptadores por proveedor + gateway en modo real.

Sin red ni coste: el transporte HTTP se INYECTA (captura la petición y devuelve una respuesta simulada), de
modo que se verifica el FORMATO exacto que se enviaría a la API del proveedor (VusionCloud/SES-imagotag) y el
mapeo de la respuesta, sin llamar a ningún servicio externo.
"""

import pytest

from src.services.esl import ESLGateway, config, registro, sync
from src.services.esl.proveedores import obtener_adaptador, proveedores_con_adaptador
from src.services.esl.proveedores.imagotag import AdaptadorImagotag

TIENDA = "TIENDA_ESL_CONECT"


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _capturador(status=200):
    reg = {}

    def transport(metodo, url, headers, cuerpo):
        reg.update(metodo=metodo, url=url, headers=headers, cuerpo=cuerpo)
        return status, "OK" if 200 <= status < 300 else "ERR"

    return reg, transport


def test_registro_adaptadores():
    assert "imagotag" in proveedores_con_adaptador()
    assert isinstance(obtener_adaptador("imagotag"), AdaptadorImagotag)
    # proveedor sin adaptador propio → cae al genérico (no rompe)
    assert obtener_adaptador("solum").codigo == "rest_generico"
    assert obtener_adaptador(None).codigo == "rest_generico"


def test_imagotag_construye_request_vusioncloud():
    reg, transport = _capturador(200)
    ctx = {"endpoint": "https://api.vusion.io/v3", "store_id": "S-42", "credencial": "TOK"}
    res = AdaptadorImagotag().push("LBL-9", {"codigo": "ART1", "precio": 3.5, "plantilla": "P1"}, ctx, transport)
    assert res["ok"] and res["estado"] == "actualizada"
    assert reg["metodo"] == "POST"
    assert reg["url"] == "https://api.vusion.io/v3/stores/S-42/items"
    assert reg["headers"]["Authorization"] == "Bearer TOK"
    item = reg["cuerpo"]["items"][0]
    assert item["itemId"] == "ART1" and item["price"] == 3.5 and item["labelId"] == "LBL-9"


def test_imagotag_localizar_flash():
    reg, transport = _capturador(200)
    ctx = {"endpoint": "https://api.vusion.io/v3", "store_id": "S-1", "credencial": "TOK"}
    r = AdaptadorImagotag().localizar("LBL-7", ctx, transport)
    assert r["ok"]
    assert reg["url"] == "https://api.vusion.io/v3/stores/S-1/labels/LBL-7/flash"


def test_gateway_real_exito_y_error():
    # 2xx → actualizada
    reg, ok_t = _capturador(200)
    gw = ESLGateway(proveedor="imagotag", endpoint="https://api.vusion.io/v3", store_id="S1",
                    credencial="K", modo_simulado=False, transport=ok_t)
    assert gw.modo_simulado is False
    assert gw.push("L1", {"codigo": "A", "precio": 1})["ok"] is True
    # 5xx → error (nunca marca actualizada sin confirmación)
    _reg, err_t = _capturador(500)
    gw_err = ESLGateway(proveedor="imagotag", endpoint="https://api.vusion.io/v3", store_id="S1",
                        credencial="K", modo_simulado=False, transport=err_t)
    r = gw_err.push("L1", {"codigo": "A", "precio": 1})
    assert r["ok"] is False and r["estado"] == "error"


def test_sync_real_end_to_end(fab, emp, db, monkeypatch):
    """Flujo completo por el camino REAL: config no-simulada + proveedor imagotag → sincronizar empuja por el
    transporte (monkeypatcheado) y marca ACTUALIZADA con el precio, sin tocar la red."""
    reg, transport = _capturador(200)
    monkeypatch.setattr("src.services.esl.gateway._http_transport", transport)

    fab._borrar("esl_config", "id_empresa", emp)
    config.guardar_config(proveedor="imagotag", endpoint="https://api.vusion.io/v3", store_id="S-9",
                          credencial="APIKEY", modo_simulado=False, id_empresa=emp, id_tienda=TIENDA)

    cod = fab.articulo(nombre="Refresco", id_empresa=emp, precio=1.25)
    registro.vincular(cod, "LBL-RT", id_empresa=emp, id_tienda=TIENDA)
    fab._borrar("esl_labels", "label_id", "LBL-RT")

    r = sync.sincronizar(id_empresa=emp, id_tienda=TIENDA)
    assert r["ok"] == 1 and r["error"] == 0
    # se construyó la petición VusionCloud real
    assert reg["url"] == "https://api.vusion.io/v3/stores/S-9/items"
    assert reg["cuerpo"]["items"][0]["price"] == 1.25
    # y quedó marcada ACTUALIZADA con el precio sincronizado
    lab = [l for l in registro.listar(id_empresa=emp, id_tienda=TIENDA) if l["label_id"] == "LBL-RT"][0]
    assert lab["estado"] == "ACTUALIZADA" and abs(float(lab["precio_sincronizado"]) - 1.25) < 1e-4


def test_sync_real_error_marca_error(fab, emp, monkeypatch):
    _reg, transport = _capturador(503)
    monkeypatch.setattr("src.services.esl.gateway._http_transport", transport)
    fab._borrar("esl_config", "id_empresa", emp)
    config.guardar_config(proveedor="imagotag", endpoint="https://api.vusion.io/v3", store_id="S-9",
                          credencial="APIKEY", modo_simulado=False, id_empresa=emp, id_tienda=TIENDA)
    cod = fab.articulo(nombre="Galletas", id_empresa=emp, precio=2.0)
    registro.vincular(cod, "LBL-ERR", id_empresa=emp, id_tienda=TIENDA)
    fab._borrar("esl_labels", "label_id", "LBL-ERR")
    r = sync.sincronizar(id_empresa=emp, id_tienda=TIENDA)
    assert r["error"] == 1 and r["ok"] == 0
    lab = [l for l in registro.listar(id_empresa=emp, id_tienda=TIENDA) if l["label_id"] == "LBL-ERR"][0]
    assert lab["estado"] == "ERROR" and lab["precio_sincronizado"] is None
