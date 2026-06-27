"""
Endurecimiento OAuth del correo corporativo: resolución del client Google sin JSON en disco.
Verifica el orden de prioridad env -> secret_manager -> GOOGLE_OAUTH_CLIENT_FILE ->
documentos/google_oauth_client.json y la compatibilidad retroactiva. No usa BD ni red.
"""

import json
import os

import pytest

from src.services.correo import servicio as S
from src.services.seguridad import secret_manager as SM

_VARS = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_FILE")


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    """Aísla cada test: sin variables OAuth. Con el entorno limpio, el secret_manager real
    (backend fernet) resuelve por env y devuelve None salvo que un test lo sustituya."""
    for v in _VARS:
        monkeypatch.delenv(v, raising=False)
    yield


def test_1_variables_entorno(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid-env")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "csec-env")
    r = S._resolver_client_oauth()
    assert r == {"client_id": "cid-env", "client_secret": "csec-env", "origen": "env"}


def test_2_secret_manager(monkeypatch):
    secretos = {"GOOGLE_OAUTH_CLIENT_ID": "cid-sm", "GOOGLE_OAUTH_CLIENT_SECRET": "csec-sm"}
    monkeypatch.setattr(SM, "obtener_secreto", lambda k, default=None: secretos.get(k, default))
    r = S._resolver_client_oauth()
    assert r["origen"] == "secret_manager" and r["client_id"] == "cid-sm" and r["client_secret"] == "csec-sm"


def test_3_fallback_client_file(monkeypatch, tmp_path):
    f = tmp_path / "client.json"
    f.write_text(json.dumps({"installed": {"client_id": "cid-f", "client_secret": "csec-f"}}))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_FILE", str(f))
    r = S._resolver_client_oauth()
    assert r["origen"] == "file" and r["ruta_fichero"] == str(f)


def test_4_fallback_documentos(monkeypatch, tmp_path):
    # Simula instalación antigua: solo documentos/google_oauth_client.json.
    (tmp_path / "google_oauth_client.json").write_text(
        json.dumps({"installed": {"client_id": "cid-doc", "client_secret": "csec-doc"}}))
    monkeypatch.setattr(S, "_dir_documentos", lambda: str(tmp_path))
    r = S._resolver_client_oauth()
    assert r["origen"] == "file" and r["ruta_fichero"].endswith("google_oauth_client.json")


def test_5_sin_configuracion(monkeypatch, tmp_path):
    monkeypatch.setattr(S, "_dir_documentos", lambda: str(tmp_path))  # documentos vacío
    assert S._resolver_client_oauth() is None
    assert S.oauth_google_configurado() is False


def test_6_prioridad_env_sobre_secret_y_fichero(monkeypatch, tmp_path):
    # Las tres fuentes presentes: gana env.
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid-env")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "csec-env")
    monkeypatch.setattr(SM, "obtener_secreto", lambda k, default=None: "cid-sm")
    f = tmp_path / "client.json"; f.write_text("{}")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_FILE", str(f))
    assert S._resolver_client_oauth()["origen"] == "env"


def test_7_prioridad_secret_sobre_fichero(monkeypatch, tmp_path):
    # Sin env, con secret_manager y fichero: gana secret_manager.
    secretos = {"GOOGLE_OAUTH_CLIENT_ID": "cid-sm", "GOOGLE_OAUTH_CLIENT_SECRET": "csec-sm"}
    monkeypatch.setattr(SM, "obtener_secreto", lambda k, default=None: secretos.get(k, default))
    f = tmp_path / "client.json"; f.write_text("{}")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_FILE", str(f))
    assert S._resolver_client_oauth()["origen"] == "secret_manager"


def test_8_secret_manager_obtener_secreto_env(monkeypatch):
    # El secret_manager (sin vault) resuelve por variable de entorno homónima.
    from src.services.seguridad import secret_manager as SMreal
    monkeypatch.setattr(SMreal, "_backend", lambda: "fernet")
    monkeypatch.setenv("CLAVE_DEMO_X", "valor-x")
    assert SMreal.obtener_secreto("CLAVE_DEMO_X") == "valor-x"
    assert SMreal.obtener_secreto("NO_EXISTE_Y", default="def") == "def"
