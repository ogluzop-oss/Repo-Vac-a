"""
Tests Etapa E · Fase E3: SDK oficial distribuible (Python + JavaScript).

Verifica que el SDK de Python es un cliente REAL de la Enterprise REST API (construye peticiones,
autentica por JWT/API Key, aplica la convención de paginación E1 e itera por cursor), que el empaquetado
pip/npm es coherente con la VERSION única declarada en `api_publica.sdks`, y que existen la
documentación, el CHANGELOG y los ejemplos. El SDK consume la API (fuente OpenAPI); no la duplica.
"""

import importlib.util
import json
import pathlib
import tomllib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SDK_PY = RAIZ / "sdk" / "python"
SDK_JS = RAIZ / "sdk" / "javascript"


def _cargar_sdk_python():
    ruta = SDK_PY / "smartmanager" / "__init__.py"
    spec = importlib.util.spec_from_file_location("smartmanager_e3_test", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Transporte:
    """Transporte inyectable: registra llamadas y devuelve respuestas programadas (sin red)."""
    def __init__(self, respuestas=None):
        self.calls = []
        self._respuestas = list(respuestas or [(200, {"data": [], "next_cursor": None})])

    def __call__(self, method, url, params, cuerpo, headers):
        self.calls.append({"method": method, "url": url, "params": params, "json": cuerpo,
                           "headers": headers})
        return self._respuestas[min(len(self.calls) - 1, len(self._respuestas) - 1)]


# ── Cliente Python real ───────────────────────────────────────────────────────
def test_list_construye_peticion_y_autentica_jwt():
    sdk = _cargar_sdk_python()
    t = _Transporte([(200, {"data": [{"id": 1}], "total": 1, "next_cursor": None})])
    c = sdk.Client("https://x/api/v1", token="TK", transporte=t)
    r = c.communications.list(limit=20, sort="fecha", order="desc")
    assert r["data"] == [{"id": 1}]
    llamada = t.calls[0]
    assert llamada["method"] == "GET"
    assert llamada["url"].startswith("https://x/api/v1/communications?")
    assert "limit=20" in llamada["url"] and "sort=fecha" in llamada["url"] and "order=desc" in llamada["url"]
    assert llamada["headers"]["Authorization"] == "Bearer TK"


def test_api_key_headers():
    sdk = _cargar_sdk_python()
    t = _Transporte([(200, {"data": []})])
    c = sdk.Client("https://x/api/v1", api_key="KEY", empresa="EMP-9", transporte=t)
    c.contacts.list(q="ana")
    h = t.calls[0]["headers"]
    assert h["X-API-Key"] == "KEY" and h["X-Empresa-Id"] == "EMP-9"
    assert "Authorization" not in h


def test_create_envia_json():
    sdk = _cargar_sdk_python()
    t = _Transporte([(201, {"id": 5})])
    c = sdk.Client("https://x/api/v1", token="TK", transporte=t)
    r = c.templates.create({"codigo": "bienvenida"})
    assert r == {"id": 5}
    assert t.calls[0]["method"] == "POST" and t.calls[0]["json"] == {"codigo": "bienvenida"}


def test_paginate_sigue_cursor():
    sdk = _cargar_sdk_python()
    t = _Transporte([
        (200, {"data": [{"id": 1}, {"id": 2}], "next_cursor": "c2"}),
        (200, {"data": [{"id": 3}], "next_cursor": None}),
    ])
    c = sdk.Client("https://x/api/v1", token="TK", transporte=t)
    ids = [d["id"] for d in c.contacts.paginate()]
    assert ids == [1, 2, 3]
    assert t.calls[1]["params"].get("cursor") == "c2"     # 2ª página pidió el cursor devuelto


def test_paginate_respuesta_legacy_lista():
    sdk = _cargar_sdk_python()
    t = _Transporte([(200, [{"id": 1}, {"id": 2}])])       # lista simple (sin sobre)
    c = sdk.Client("https://x/api/v1", token="TK", transporte=t)
    assert [d["id"] for d in c.contacts.paginate()] == [1, 2]


def test_error_http_lanza_excepcion():
    sdk = _cargar_sdk_python()
    t = _Transporte([(403, {"error": "forbidden"})])
    c = sdk.Client("https://x/api/v1", token="TK", transporte=t)
    with pytest.raises(sdk.SmartManagerError) as ei:
        c.commerce.list()
    assert ei.value.status == 403 and ei.value.payload == {"error": "forbidden"}


# ── Empaquetado + versionado único ────────────────────────────────────────────
def test_version_unica_coherente():
    from src.services.api_publica import sdks
    py = _cargar_sdk_python()
    pyproject = tomllib.loads((SDK_PY / "pyproject.toml").read_text(encoding="utf-8"))
    pkg = json.loads((SDK_JS / "package.json").read_text(encoding="utf-8"))
    assert sdks.VERSION == py.__version__ == pyproject["project"]["version"] == pkg["version"]
    assert pyproject["project"]["name"] == "smartmanager"
    assert pkg["name"] == "@smartmanager/sdk"


def test_metadata_paquetes():
    from src.services.api_publica import sdks
    meta = sdks.metadata()
    assert meta["version"] == sdks.VERSION
    assert set(meta["distribuibles"]) == {"python", "javascript"}
    assert sdks.paquete("python")["gestor"] == "pip"
    assert sdks.paquete("javascript")["gestor"] == "npm"
    assert sdks.paquete("cobol") is None


def test_artefactos_documentacion_y_ejemplos():
    for f in (SDK_PY / "README.md", SDK_PY / "CHANGELOG.md", SDK_PY / "examples" / "quickstart.py",
              SDK_JS / "README.md", SDK_JS / "CHANGELOG.md", SDK_JS / "examples" / "quickstart.mjs",
              SDK_JS / "src" / "index.js", RAIZ / "sdk" / "README.md"):
        assert f.exists() and f.stat().st_size > 0, f"falta artefacto: {f}"
