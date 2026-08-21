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


def test_presets_catalogo():
    assert set(B2B.PRESETS) >= {"consentio", "choco", "prezo", "b2brouter", "haddock", "rest", "simulado"}
    # Los presets de plataforma fijan un endpoint y usan el adaptador REST.
    assert B2B.preset("consentio")["endpoint"] and B2B._adapter_de("consentio") == "rest"
    assert B2B.preset("consentio")["oauth"] is True
    assert B2B._adapter_de("simulado") == "simulado"
    assert B2B.preset("rest")["endpoint"] == ""   # REST personalizado: el usuario lo escribe


def test_probar_conexion():
    # Simulado → ok. REST sin credenciales → falla (faltan claves), nunca lanza.
    assert B2B.probar_conexion(config={"proveedor": "simulado"})["ok"] is True
    r = B2B.probar_conexion(config={"proveedor": "consentio"})
    assert r["ok"] is False and "credenciales" in r["mensaje"].lower()
