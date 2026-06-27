"""
BLOQUE 8 — capa portable de SO, perfil táctil y escáner universal.
Tests deterministas, sin hardware ni SO real distinto del host.
"""
import importlib

import pytest

from src.utils import plataforma, perfil_tactil
from src.services.perifericos import escaner_universal as eu


# ----------------------------- plataforma -----------------------------
def test_abrir_archivo_windows(monkeypatch):
    llamadas = []
    monkeypatch.setattr(plataforma, "ES_WINDOWS", True)
    monkeypatch.setattr(plataforma, "ES_MAC", False)
    monkeypatch.setattr(plataforma, "ES_LINUX", False)
    monkeypatch.setattr(plataforma.os, "startfile", lambda r, *a: llamadas.append((r, a)), raising=False)
    assert plataforma.abrir_archivo("doc.pdf") is True
    assert llamadas and llamadas[0][0] == "doc.pdf"


def test_abrir_archivo_macos(monkeypatch):
    cmd = []
    monkeypatch.setattr(plataforma, "ES_WINDOWS", False)
    monkeypatch.setattr(plataforma, "ES_MAC", True)
    monkeypatch.setattr(plataforma.subprocess, "Popen", lambda args, *a, **k: cmd.append(args))
    assert plataforma.abrir_archivo("doc.pdf") is True
    assert cmd[0] == ["open", "doc.pdf"]


def test_abrir_archivo_linux(monkeypatch):
    cmd = []
    monkeypatch.setattr(plataforma, "ES_WINDOWS", False)
    monkeypatch.setattr(plataforma, "ES_MAC", False)
    monkeypatch.setattr(plataforma, "ES_LINUX", True)
    monkeypatch.setattr(plataforma.shutil, "which", lambda x: "/usr/bin/xdg-open")
    monkeypatch.setattr(plataforma.subprocess, "Popen", lambda args, *a, **k: cmd.append(args))
    assert plataforma.abrir_archivo("doc.pdf") is True
    assert cmd[0] == ["xdg-open", "doc.pdf"]


def test_abrir_archivo_linux_sin_xdg_degrada(monkeypatch):
    monkeypatch.setattr(plataforma, "ES_WINDOWS", False)
    monkeypatch.setattr(plataforma, "ES_MAC", False)
    monkeypatch.setattr(plataforma.shutil, "which", lambda x: None)
    assert plataforma.abrir_archivo("doc.pdf") is False  # no rompe, degrada


def test_abrir_archivo_vacio():
    assert plataforma.abrir_archivo("") is False


def test_imprimir_inexistente():
    assert plataforma.imprimir_archivo("no_existe_zzz.pdf") is False


def test_imprimir_linux_lpr(monkeypatch, tmp_path):
    f = tmp_path / "t.pdf"; f.write_text("x")
    cmd = []
    monkeypatch.setattr(plataforma, "ES_WINDOWS", False)
    monkeypatch.setattr(plataforma.shutil, "which", lambda x: "/usr/bin/lpr")
    monkeypatch.setattr(plataforma.subprocess, "Popen", lambda args, *a, **k: cmd.append(args))
    assert plataforma.imprimir_archivo(str(f)) is True
    assert cmd[0] == ["lpr", str(f)]


# ----------------------------- perfil táctil -----------------------------
def test_perfil_por_defecto(monkeypatch):
    monkeypatch.delenv("SMART_MANAGER_PERFIL_TACTIL", raising=False)
    importlib.reload(perfil_tactil)
    assert perfil_tactil.perfil_actual() == perfil_tactil.NORMAL
    assert perfil_tactil.altura_min_control() == 0
    assert perfil_tactil.es_tactil() is False


def test_perfil_desde_env(monkeypatch):
    monkeypatch.setenv("SMART_MANAGER_PERFIL_TACTIL", "TPV")
    importlib.reload(perfil_tactil)
    assert perfil_tactil.perfil_actual() == perfil_tactil.TPV
    assert perfil_tactil.altura_min_control() == 56
    assert perfil_tactil.es_tactil() is True


def test_set_perfil_y_minimos():
    importlib.reload(perfil_tactil)
    assert perfil_tactil.set_perfil("tactil") == "tactil"
    assert perfil_tactil.altura_min_control() == 48
    assert perfil_tactil.set_perfil("pda") == "pda"
    assert perfil_tactil.altura_min_control() == 44
    assert perfil_tactil.set_perfil("desconocido") == "normal"  # valor inválido -> normal


# ----------------------------- escáner universal -----------------------------
def test_escaner_emite_con_terminador():
    b = eu.BufferEscaner()
    for ch in "8412345678905":
        assert b.pulsar(ch) is None
    assert b.pulsar("\n") == "8412345678905"


def test_escaner_inyeccion_en_bloque():
    b = eu.BufferEscaner()
    assert b.pulsar("8412345678905\n") == "8412345678905"


def test_escaner_timing_reinicia_tecleo_humano():
    b = eu.BufferEscaner(umbral_ms=60)
    b.pulsar("1", t_ms=0)
    b.pulsar("2", t_ms=10)     # ráfaga inicial
    b.pulsar("3", t_ms=1000)   # pausa larga -> descarta "12" (tecleo humano)
    b.pulsar("4", t_ms=1010)
    b.pulsar("5", t_ms=1020)
    # Solo sobrevive la ráfaga posterior "345": se demuestra que "12" se descartó.
    assert b.pulsar("\n", t_ms=1030) == "345"


def test_escaner_longitud_minima():
    b = eu.BufferEscaner(longitud_min=3)
    b.pulsar("1"); b.pulsar("2")
    assert b.pulsar("\n") is None  # "12" demasiado corto


def test_normalizar_codigo():
    assert eu.normalizar_codigo("  abc123\n") == "abc123"
    assert eu.normalizar_codigo("") is None
    assert eu.normalizar_codigo(None) is None
