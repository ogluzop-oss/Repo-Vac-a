"""
Tests · Capacidades avanzadas — lo genuinamente verificable en este entorno.

  · API PÚBLICA (Fase 7): OAuth2 client-credentials real (registrar app → emitir token acotado a scopes →
    verificar scope) + documento OpenAPI. Reutiliza la seguridad JWT existente (`seguridad.tokens`).
  · IA (Fase 1/10): el origen de la predicción se distingue HONESTAMENTE (heurística vs ML); por defecto
    es heurística y `es_ml=False` — nunca se presenta una heurística como IA/ML.

Las demás capacidades (móvil nativo, Canal Web con hosting real, cloud multi-región, conectores externos
con credenciales reales) tienen bloqueos EXTERNOS y se documentan en CERTIFICACION_CAPACIDADES_AVANZADAS.md,
no se falsean con mocks.
"""

import pytest

pytestmark = pytest.mark.db

EMP = "T-APIP-1"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            try:
                cur.execute("DELETE FROM api_dev_apps WHERE id_empresa=%s", (EMP,))
            except Exception:
                pass
            c.commit()
    _b()
    yield
    _b()


def test_api_publica_oauth2_scopes(limpia):
    from src.services.api_publica import developer, oauth

    # App con SOLO lectura de pedidos (la escritura NO se le concede).
    r = developer.registrar_app("Integración de prueba", id_empresa=EMP, scopes=["read:orders"])
    assert r.get("ok") and r.get("client_id") and r.get("client_secret")
    cid, csec = r["client_id"], r["client_secret"]

    # Token client-credentials acotado a los scopes concedidos.
    tok = oauth.emitir_token(cid, csec, scopes=["read:orders"])
    assert tok and tok.get("access_token") and tok.get("token_type") == "Bearer"
    assert "read:orders" in tok.get("scopes", [])

    # El scope concedido se verifica; uno NO concedido a la app, no.
    assert oauth.verificar_scope(tok["access_token"], "read:orders") is True
    assert oauth.verificar_scope(tok["access_token"], "write:orders") is False

    # Credenciales incorrectas → sin token (no se emite nada).
    assert oauth.emitir_token(cid, "csec_incorrecto", scopes=["read:orders"]) is None


def test_api_publica_openapi():
    from src.services.api_publica import openapi_publica
    doc = openapi_publica.documento("/api/v1")
    assert isinstance(doc, dict) and doc.get("openapi", "").startswith("3.")
    assert "info" in doc and "paths" in doc
    assert openapi_publica.swagger_url("/api/v1").endswith("/openapi.json")


def test_ia_origen_honesto():
    """El origen de la predicción se identifica: por defecto HEURÍSTICA (no ML)."""
    from src.services.prediccion import heuristicas
    info = heuristicas.motor_activo()
    assert info["tipo"] == "heuristica" and info["es_ml"] is False
    assert info["motor"] in ("heuristico", "base")

    # Al enchufar un estimador ML real, el origen pasa a 'ml' (es_ml=True).
    class _EstimadorMLFake(heuristicas.Estimador):
        nombre = "prophet"
        def predecir(self, valores, pasos=1):
            return 42.0
    previo = heuristicas.estimador()
    try:
        heuristicas.set_estimador(_EstimadorMLFake())
        info_ml = heuristicas.motor_activo()
        assert info_ml["tipo"] == "ml" and info_ml["es_ml"] is True and info_ml["motor"] == "prophet"
    finally:
        heuristicas.set_estimador(previo)   # restaura el motor por defecto
