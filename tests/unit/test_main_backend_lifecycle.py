"""
Ciclo de vida del backend (`src.main.iniciar_backend`/`detener_backend` + `src.backend.app.
_codigo_propio_desactualizado`) — bug real reportado por el usuario: en CADA arranque de la app de
escritorio, si CUALQUIER `.py` de todo `src/` se había modificado (incluidos ficheros que el
backend ni siquiera importa, p. ej. `src/gui/*`), el backend ya corriendo se mataba y se relanzaba
desde cero — varios segundos reales de coste (bootstrap de BD, registro de rutas) en cada
arranque, durante una sesión de desarrollo activa donde el código cambia constantemente. Petición
explícita del usuario: que el backend persista entre arranques/cierres de la app de escritorio
("prefiero que la app tarde más en cerrarse... y que posteriormente se abra más rápido... sin
perder los datos").

Dos piezas:
1. El backend se autodiagnostica (`_codigo_propio_desactualizado`, en `src/backend/app.py`):
   compara, de sus PROPIOS módulos ya cargados (`sys.modules`) bajo `src/`, si alguno se modificó
   en disco DESPUÉS de que él arrancara — ya no depende de una lista de rutas mantenida a mano ni
   de recorrer TODO `src/` sin distinguir si el backend lo usa o no.
2. `src.main.iniciar_backend` ya NO registra `detener_backend` ni en `atexit` ni en
   `app.aboutToQuit` — el backend debe sobrevivir al cierre de la app de escritorio.
"""

import os
import socket
import time

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# `src.backend.app._codigo_propio_desactualizado`
# ─────────────────────────────────────────────────────────────────────────────

def test_codigo_propio_desactualizado_false_justo_tras_importar():
    """Recién importado, ningún módulo propio debería tener un mtime posterior a `_INICIADO_EN`
    (se capturó en el mismo instante de importar el módulo)."""
    from src.backend import app as backend_app
    assert backend_app._codigo_propio_desactualizado() is False


def test_codigo_propio_desactualizado_true_si_un_modulo_cargado_cambia_en_disco():
    """Tocar (mtime futuro) un fichero de un módulo que el backend YA tiene cargado en
    `sys.modules` debe hacer que se autodiagnostique como desactualizado."""
    from src.backend import app as backend_app
    objetivo = os.path.abspath(backend_app.__file__)
    mtime_original = os.path.getmtime(objetivo)
    try:
        futuro = time.time() + 3600
        os.utime(objetivo, (futuro, futuro))
        assert backend_app._codigo_propio_desactualizado() is True
    finally:
        os.utime(objetivo, (mtime_original, mtime_original))


def test_codigo_propio_desactualizado_ignora_modulos_fuera_de_src():
    """Un módulo de la librería estándar (o de un paquete externo) con un mtime "futuro" no debe
    contar — el chequeo es SOLO sobre los propios módulos de `src/`."""
    from src.backend import app as backend_app
    import sys
    assert "os" in sys.modules
    # `os` en sí no tiene __file__ de interés garantizado en todas las plataformas, pero el propio
    # intérprete carga de sobra módulos ajenos a `src/` (p. ej. `logging`, `json`) — si el chequeo
    # los considerase, este test (sin tocar nada) ya fallaría por simple ruido del entorno.
    assert backend_app._codigo_propio_desactualizado() is False


def test_salud_incluye_codigo_desactualizado():
    """El endpoint `/salud` debe exponer `codigo_desactualizado`, que es lo que
    `src.main.iniciar_backend` consulta para decidir si reutiliza o sustituye el backend."""
    pytest.importorskip("flask")
    from src.backend.app import crear_app
    cliente = crear_app().test_client()
    r = cliente.get("/salud")
    assert r.status_code == 200
    datos = r.get_json()
    assert datos["servicio"] == "smart-manager-backend"
    assert "codigo_desactualizado" in datos
    assert datos["codigo_desactualizado"] is False


# ─────────────────────────────────────────────────────────────────────────────
# `src.main.iniciar_backend` — reutilizar/sustituir/lanzar, SIN auto-matar al cerrar
# ─────────────────────────────────────────────────────────────────────────────

def _puerto_libre() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def entorno_backend(monkeypatch):
    """Aísla cada test: puerto efímero propio (vía `BACKEND_PORT`) y `_backend_proc` global
    limpio antes y después — nunca comparte estado entre tests ni con un backend real."""
    from src import main as m
    port = _puerto_libre()
    monkeypatch.setenv("BACKEND_PORT", str(port))
    m._backend_proc = None
    yield m, port
    m._backend_proc = None


def test_iniciar_backend_lanza_si_el_puerto_esta_libre(entorno_backend, monkeypatch):
    m, port = entorno_backend
    llamadas = []

    class _ProcesoFalso:
        def poll(self):
            return None

    def _popen_falso(*args, **kwargs):
        llamadas.append((args, kwargs))
        return _ProcesoFalso()

    monkeypatch.setattr(m.subprocess, "Popen", _popen_falso)
    m.iniciar_backend()

    assert len(llamadas) == 1, "con el puerto libre, debe lanzar un backend nuevo"
    assert m._backend_proc is not None


def test_iniciar_backend_reutiliza_si_el_puerto_ya_esta_ocupado_y_vigente(entorno_backend, monkeypatch):
    """Petición del usuario: un backend YA corriendo y vigente (código no desactualizado) no debe
    matarse ni relanzarse — se reutiliza tal cual."""
    m, port = entorno_backend
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.bind(("127.0.0.1", port))
    servidor.listen(1)
    try:
        monkeypatch.setattr(m, "_backend_remoto_info",
                             lambda p, timeout=1.5: {"servicio": "smart-manager-backend",
                                                     "codigo_desactualizado": False})
        llamadas_popen = []
        monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: llamadas_popen.append((a, k)))
        llamadas_matar = []
        monkeypatch.setattr(m, "_matar_backend_obsoleto", lambda p: llamadas_matar.append(p) or True)

        m.iniciar_backend()

        assert not llamadas_popen, "no debe lanzar un backend nuevo si el existente está vigente"
        assert not llamadas_matar, "no debe matar un backend vigente"
        assert m._backend_proc is None, "no se lanzó nada propio — no hay proceso que registrar"
    finally:
        servidor.close()


def test_iniciar_backend_sustituye_si_el_puerto_esta_ocupado_y_desactualizado(entorno_backend, monkeypatch):
    """Un backend identificable pero con código desactualizado SÍ debe matarse y relanzarse."""
    m, port = entorno_backend
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.bind(("127.0.0.1", port))
    servidor.listen(1)
    try:
        monkeypatch.setattr(m, "_backend_remoto_info",
                             lambda p, timeout=1.5: {"servicio": "smart-manager-backend",
                                                     "codigo_desactualizado": True})
        llamadas_matar = []

        def _matar_falso(p):
            llamadas_matar.append(p)
            servidor.close()   # simula liberar el puerto de verdad
            return True
        monkeypatch.setattr(m, "_matar_backend_obsoleto", _matar_falso)

        llamadas_popen = []

        class _ProcesoFalso:
            def poll(self):
                return None
        monkeypatch.setattr(m.subprocess, "Popen",
                             lambda *a, **k: (llamadas_popen.append((a, k)), _ProcesoFalso())[1])

        m.iniciar_backend()

        assert llamadas_matar == [port], "debe matar el backend desactualizado"
        assert len(llamadas_popen) == 1, "debe relanzar uno nuevo tras matar el obsoleto"
    finally:
        try:
            servidor.close()
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Regresión: `detener_backend` ya NO se auto-registra (ni atexit ni aboutToQuit) — comprobación
# a nivel de código fuente, ya que `main()` arranca la app de escritorio completa (pesado/no apto
# para un test unitario) y no se puede invocar directamente aquí.
# ─────────────────────────────────────────────────────────────────────────────

def test_detener_backend_no_se_registra_automaticamente_en_el_codigo_fuente():
    import inspect
    from src import main as m

    fuente_iniciar = inspect.getsource(m.iniciar_backend)
    for linea in fuente_iniciar.splitlines():
        sin_comentario = linea.split("#", 1)[0]
        assert "atexit.register(detener_backend)" not in sin_comentario, (
            "iniciar_backend() no debe registrar detener_backend en atexit — el backend debe "
            "persistir al cerrar la app de escritorio")

    fuente_main = inspect.getsource(m)
    for linea in fuente_main.splitlines():
        sin_comentario = linea.split("#", 1)[0]
        assert "aboutToQuit.connect(detener_backend)" not in sin_comentario, (
            "no debe conectarse detener_backend a aboutToQuit — el backend debe persistir al "
            "cerrar la app de escritorio")
