"""
Tests · Fase WEB-13 — Motor Enterprise de Integraciones Comerciales (solo arquitectura, nada conectado).

Verifica: matriz de capacidades, pipeline dirigido por capacidades, importación/exportación separadas,
contrato de colas (local + backends preparados), detección sin red, validación/errores/versiones,
adaptadores preparados (Hostinger/Woo/Shopify/…), auditoría canónica, y las PROHIBICIONES arquitectónicas
(sin `if plataforma ==`, sin OAuth/HTTP/webhooks/sync real).
"""

import inspect
import os
import pathlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.services.marketplace import integraciones_comerciales as ic  # noqa: E402

M = ic.motor
_MOTOR_DIR = pathlib.Path(inspect.getsourcefile(M)).parent


def _fuentes_motor():
    return {p.name: p.read_text(encoding="utf-8") for p in _MOTOR_DIR.glob("*.py")}


# ── 1 · Capacidades declarativas ──────────────────────────────────────────────
def test_capacidades_por_conector():
    assert len(M.CAPACIDADES_NOMBRES) == 14
    hos = M.capacidades("hostinger")
    assert hos.soporta("supports_web_creation") and hos.soporta("supports_ai_generation")
    assert not hos.soporta("supports_orders") and not hos.soporta("supports_products")
    woo = M.capacidades("woocommerce")
    assert woo.soporta("supports_products") and woo.soporta("supports_orders")
    assert not woo.soporta("supports_web_creation")
    # Plataforma desconocida → todas False (degradable, sin error).
    assert M.capacidades("desconocida").soportadas() == []
    assert set(M.matriz()) >= {"hostinger", "woocommerce", "shopify"}


# ── 2 · Pipeline dirigido por CAPACIDADES (no por plataforma) ─────────────────
def test_pipeline_por_capacidades():
    assert M.PASOS == ("VALIDAR", "AUTENTICAR", "DESCUBRIR", "IMPORTAR", "SINCRONIZAR",
                       "VERIFICAR", "FINALIZAR")
    woo = M.PipelineSincronizacion("woocommerce").plan()
    assert "productos" in woo["ambitos"] and "pedidos" in woo["ambitos"]
    # Hostinger no soporta datos → su plan de ámbitos es vacío (por capacidades, no por `if`).
    assert M.PipelineSincronizacion("hostinger").plan()["ambitos"] == []
    # No ejecuta nada real.
    import pytest
    with pytest.raises(NotImplementedError):
        M.PipelineSincronizacion("woocommerce").ejecutar()


# ── 3 · Importación / exportación separadas y preparadas ──────────────────────
def test_import_export_interfaces():
    import pytest
    assert set(M.importacion.IMPORTADORES) >= {"productos", "clientes", "pedidos", "stock", "precios",
                                               "estados", "transportistas", "reservas", "click_collect"}
    assert set(M.exportacion.EXPORTADORES) >= {"actualizar_stock", "crear_pedidos", "actualizar_pedidos",
                                              "actualizar_estados", "actualizar_clientes", "actualizar_precios"}
    with pytest.raises(NotImplementedError):
        M.importacion.ImportadorProductos().importar()
    with pytest.raises(NotImplementedError):
        M.exportacion.ExportadorActualizarStock().exportar({})


# ── 4 · Colas: local funcional, remotas preparadas ───────────────────────────
def test_colas_contrato():
    import pytest
    assert set(M.BACKENDS) == {"local", "redis", "sqs", "rabbitmq"}
    q = M.cola("local")
    q.encolar({"job": 1})
    assert q.tamano() == 1 and q.desencolar() == {"job": 1}
    for backend in ("redis", "sqs", "rabbitmq"):
        with pytest.raises(NotImplementedError):
            M.cola(backend).encolar({})


# ── 5 · Detección SIN red ─────────────────────────────────────────────────────
def test_deteccion_sin_red():
    r = M.detectar("https://miempresa.com")
    assert r["requiere_sondeo"] is True and r["plataforma"] is None   # sin señales → no adivina, no navega
    r2 = M.detectar("https://x.com", {"html": "cargando /wp-json/wc/ store"})
    assert r2["plataforma"] == "woocommerce" and r2["requiere_sondeo"] is False


# ── 6 · Validación / errores / versiones ──────────────────────────────────────
def test_validacion_errores_versiones():
    assert M.COMPROBACIONES == ("url", "credenciales", "version", "api", "permisos", "estado", "ssl")
    inf = M.Validador("shopify").validar()
    assert inf["estado"] == "PREPARADO" and all(v == "preparado" for v in inf["comprobaciones"].values())
    assert set(M.CODIGOS) == {"AUTH_ERROR", "NETWORK_ERROR", "TIMEOUT", "API_ERROR", "RATE_LIMIT",
                              "UNSUPPORTED_VERSION", "INVALID_CONFIGURATION", "INVALID_DOMAIN",
                              "MISSING_CREDENTIALS"}
    err = M.IntegracionError(M.CodigoError.AUTH_ERROR, "x", plataforma="woo")
    assert err.to_dict()["codigo"] == "AUTH_ERROR"
    v = M.VersionInfo(minimum_version="3.5", maximum_version="9.0")
    assert v.compatible("4.0") and not v.compatible("3.0") and not v.compatible("10.0")


# ── 7 · Adaptadores preparados (vacíos, no conectan) ─────────────────────────
def test_adaptadores_preparados():
    import pytest
    esperadas = {"hostinger", "woocommerce", "shopify", "prestashop", "magento", "opencart",
                 "amazon", "ebay", "miravia", "aliexpress", "tiktok_shop"}
    assert esperadas <= set(M.ADAPTADORES)
    for plat in esperadas:
        a = M.adaptador(plat)
        assert a.disponible() is False
        assert a.descriptor()["estado"] == "PREPARADO"
        with pytest.raises(NotImplementedError):
            a.conectar({})            # contrato heredado, sin conexión
    # Hostinger: creación IA preparada (no conecta).
    with pytest.raises(NotImplementedError):
        M.adaptador("hostinger").crear_web_ia(None)


# ── 8 · Auditoría canónica ────────────────────────────────────────────────────
def test_auditoria_eventos():
    assert M.EVENTOS == ("INTEGRATION_CREATED", "INTEGRATION_VALIDATED", "INTEGRATION_SYNC_STARTED",
                         "INTEGRATION_SYNC_FINISHED", "INTEGRATION_DISABLED", "INTEGRATION_ENABLED")
    assert M.registrar_evento("INTEGRATION_CREATED", id_empresa="E1", plataforma="woo") in (True, False)


# ── 9 · Prohibiciones arquitectónicas (grep del código fuente del motor) ──────
def test_arquitectura_desacoplada_sin_prohibidos():
    fuentes = _fuentes_motor()
    todo = "\n".join(fuentes.values()).lower()
    # Sin `if plataforma ==` (arquitectura por capacidades/registro).
    assert "if plataforma ==" not in todo and 'plataforma == "' not in todo
    # Sin clientes HTTP / OAuth / websockets REALES (import de librería de red), no en prosa.
    for prohibido in ("import requests", "import urllib.request", "from urllib", "import httpx",
                      "import aiohttp", "import oauthlib", "requests_oauthlib", "import websocket"):
        assert prohibido not in todo, prohibido
    # El motor está registrado en la fachada (N7).
    assert hasattr(ic, "motor") and hasattr(ic, "capacidades")
