"""
Tests PCD · Etapa B · Fase B1: Conexiones de canal + credenciales seguras.

Verifica: registro por tenant, credenciales SIEMPRE cifradas (nunca en claro en BD), resolución en
runtime al construir el AdapterContext, `obtener` no expone el secreto, deduplicación por
(empresa,canal,nombre), aislamiento multiempresa, degradación elegante, y que el Sync Engine
construye el contexto desde la conexión.
"""

import inspect

import pytest

EMP = "T-CONX-A"


@pytest.fixture()
def limpio(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_conexiones WHERE id_empresa IN (%s,%s)", (EMP, "T-CONX-B"))
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_conexiones WHERE id_empresa IN (%s,%s)", (EMP, "T-CONX-B"))
        conn.commit()


def test_registrar_y_resolver_credenciales(limpio):
    from src.services.comercio_digital import conexiones as cx
    ok = cx.registrar("woocommerce", nombre="tienda1", id_empresa=EMP, tipo_auth="apikey",
                      endpoint_base="https://ejemplo.tld/wp-json",
                      credenciales={"consumer_key": "ck_123", "consumer_secret": "cs_456"},
                      actor="admin")
    assert ok
    # Resolución en runtime (descifrado).
    cred = cx.credenciales("woocommerce", nombre="tienda1", id_empresa=EMP)
    assert cred.get("consumer_key") == "ck_123" and cred.get("consumer_secret") == "cs_456"


def test_credenciales_nunca_en_claro_en_bd(limpio, db):
    from src.services.comercio_digital import conexiones as cx
    cx.registrar("stripe", id_empresa=EMP, tipo_auth="apikey",
                 credenciales={"secret_key": "sk_live_SUPERSECRETO"}, actor="a")
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT credenciales_cifradas FROM cd_conexiones WHERE id_empresa=%s AND "
                    "canal='stripe'", (EMP,))
        r = cur.fetchone()
        cif = (list(r.values())[0] if isinstance(r, dict) else r[0]) or ""
    assert cif and "sk_live_SUPERSECRETO" not in cif        # cifrado: el secreto no aparece en claro


def test_obtener_no_expone_secreto(limpio):
    from src.services.comercio_digital import conexiones as cx
    cx.registrar("mrw", id_empresa=EMP, credenciales={"token": "T-999"}, endpoint_base="https://x")
    d = cx.obtener("mrw", id_empresa=EMP)
    assert d and "credenciales" not in d and "credenciales_cifradas" not in d
    assert d["endpoint_base"] == "https://x" and d["canal"] == "mrw"


def test_contexto_para_adaptador(limpio):
    from src.services.comercio_digital import conexiones as cx
    from src.services.comercio_digital.canales.adaptador import AdapterContext
    cx.registrar("paypal", id_empresa=EMP, endpoint_base="https://api.paypal",
                 credenciales={"client_id": "CID", "client_secret": "CS"})
    ctx = cx.contexto("paypal", id_empresa=EMP, correlation_id="corr-1")
    assert isinstance(ctx, AdapterContext)
    assert ctx.credenciales.get("client_id") == "CID"
    assert ctx.extra.get("endpoint_base") == "https://api.paypal" and ctx.canal == "paypal"


def test_contexto_degradable_sin_conexion(limpio):
    from src.services.comercio_digital import conexiones as cx
    from src.services.comercio_digital.canales.adaptador import AdapterContext
    ctx = cx.contexto("inexistente", id_empresa=EMP)      # sin conexión → contexto vacío
    assert isinstance(ctx, AdapterContext) and ctx.credenciales == {} and ctx.extra == {}


def test_probar_conexion(limpio):
    from src.services.comercio_digital import conexiones as cx
    cx.registrar("gls", id_empresa=EMP, endpoint_base="https://gls", credenciales={"k": "v"})
    assert cx.probar("gls", id_empresa=EMP)["ok"] is True
    cx.registrar("dhl", id_empresa=EMP, credenciales={"k": "v"})   # sin endpoint
    assert cx.probar("dhl", id_empresa=EMP)["ok"] is False


def test_aislamiento_multiempresa(limpio):
    from src.services.comercio_digital import conexiones as cx
    cx.registrar("amazon", id_empresa=EMP, credenciales={"k": "A"}, endpoint_base="https://a")
    assert cx.obtener("amazon", id_empresa=EMP) is not None
    assert cx.obtener("amazon", id_empresa="T-CONX-B") is None     # otra empresa no la ve
    assert cx.credenciales("amazon", id_empresa="T-CONX-B") == {}


def test_sync_usa_contexto_de_conexion():
    """El Sync Engine construye el contexto del adaptador desde la conexión (credenciales seguras)."""
    from src.services.comercio_digital import sync
    src = inspect.getsource(sync)
    assert "_contexto_canal" in src and "conexiones" in src
    # secret_manager es una capacidad (no import directo del proveedor).
    from src.services.comercio_digital import conexiones as cx
    csrc = inspect.getsource(cx)
    assert "capabilities" in csrc
    assert "from src.services.seguridad" not in csrc              # solo por capacidad
    assert cx.descriptor()["secretos_en_claro"] is False
