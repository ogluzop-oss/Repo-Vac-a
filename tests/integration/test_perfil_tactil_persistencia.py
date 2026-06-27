"""
BLOQUE 8.3 — selector de perfil táctil: persistencia por usuario, carga al inicio y
exposición en Configuración. Importa src.db.preferencias y src.gui.gestion_usuarios
(deps completas), por eso vive fuera de test_plataforma_b8.py (que corre en el CI Multi-OS
con dependencias mínimas). Aquí se ejecuta en la suite completa.
"""
import importlib

from src.utils import perfil_tactil


def test_guardar_y_cargar_preferencia_por_usuario(monkeypatch):
    from src.db import preferencias as P
    store = {}
    monkeypatch.delenv("SMART_MANAGER_PERFIL_TACTIL", raising=False)
    monkeypatch.setattr(P, "guardar", lambda uid, k, v: bool(store.__setitem__((uid, k), v)) or True)
    monkeypatch.setattr(P, "obtener", lambda uid, k, d=None: store.get((uid, k), d))
    assert perfil_tactil.guardar_en_preferencias(7, "tpv") == "tpv"
    assert store[(7, "perfil_tactil")] == "tpv"
    perfil_tactil.set_perfil("normal")
    assert perfil_tactil.cargar_desde_preferencias(7) == "tpv"   # se recupera del usuario
    perfil_tactil.set_perfil("normal")


def test_env_override_gana_sobre_preferencia(monkeypatch):
    from src.db import preferencias as P
    monkeypatch.setattr(P, "obtener", lambda uid, k, d=None: "tpv")
    monkeypatch.setenv("SMART_MANAGER_PERFIL_TACTIL", "pda")
    importlib.reload(perfil_tactil)
    assert perfil_tactil.cargar_desde_preferencias(7) == "pda"
    monkeypatch.delenv("SMART_MANAGER_PERFIL_TACTIL", raising=False)
    importlib.reload(perfil_tactil)


def test_preferencia_invalida_degrada_a_normal(monkeypatch):
    from src.db import preferencias as P
    monkeypatch.delenv("SMART_MANAGER_PERFIL_TACTIL", raising=False)
    monkeypatch.setattr(P, "obtener", lambda uid, k, d=None: "valor_basura")
    perfil_tactil.set_perfil("tpv")
    # un valor inválido no cambia nada coherente -> queda un perfil válido
    res = perfil_tactil.cargar_desde_preferencias(7)
    assert res in perfil_tactil.PERFILES
    perfil_tactil.set_perfil("normal")


def test_configuracion_expone_selector_tactil():
    import src.gui.gestion_usuarios as gu
    assert hasattr(gu.ConfiguracionWindow, "_crear_page_modo_tactil")
    assert hasattr(gu.ConfiguracionWindow, "_aplicar_perfil_tactil")


def test_tab_modo_tactil_registrada():
    # La pestaña debe estar declarada en el listado de tabs de Configuración.
    src = open("src/gui/gestion_usuarios.py", encoding="utf-8").read()
    assert "cfg.tab_modo_tactil" in src and "_crear_page_modo_tactil" in src
