"""Conector B2B agnóstico (Fase 2) — registro, detección de configuración y degradado. (unit, sin db)

Cubre: adaptadores registrados (rest/simulado); ConectorREST requiere endpoint+api_key; el simulado despacha
órdenes con id de confirmación; y las funciones de módulo degradan (catálogo vacío, orden simulada) cuando no
hay conector configurado.
"""

from src.services.compras import b2b_client as B2B


def test_adaptadores_registrados():
    assert set(B2B._REGISTRO) >= {"rest", "simulado"}


def test_conector_rest_requiere_credenciales():
    assert B2B.ConectorREST({}).configurado() is False
    assert B2B.ConectorREST({"endpoint": "https://api.x", "api_key": "k"}).configurado() is True


def test_simulado_despacha_orden_con_id():
    r = B2B.ConectorSimulado({}).enviar_orden_compra({"lineas": []})
    assert r["ok"] is True and r["id_externo"].startswith("SIM-") and r["estado"] == "simulado"


def test_modulo_degrada_sin_config(monkeypatch):
    import src.db.compras_b2b as cfgdb
    monkeypatch.setattr(cfgdb, "obtener_config", lambda id_empresa=None: {"proveedor": "rest"})
    # Sin endpoint/api_key → catálogo vacío y la orden va por el simulado (nunca lanza).
    assert B2B.obtener_catalogo("ART1", id_empresa="E1") == []
    assert B2B.enviar_orden_compra({"lineas": []}, id_empresa="E1")["estado"] == "simulado"
    assert B2B.disponible("E1") is False


def test_disponible_con_config(monkeypatch):
    import src.db.compras_b2b as cfgdb
    monkeypatch.setattr(cfgdb, "obtener_config",
                        lambda id_empresa=None: {"proveedor": "rest", "endpoint": "https://api.x",
                                                 "api_key": "k"})
    assert B2B.disponible("E1") is True
