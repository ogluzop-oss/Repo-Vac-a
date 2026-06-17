"""E1.6 · Observabilidad mínima operativa: salud, eventos y diagnóstico."""

import logging

import pytest

pytestmark = pytest.mark.db


def test_estado_sistema_con_bd(db):
    from src.utils import observabilidad as O
    e = O.estado_sistema()
    assert e["db_ok"] is True                      # BD de pruebas conectada
    assert e["migracion_actual"]                   # hay migraciones aplicadas
    assert set(e.keys()) >= {"db_ok", "migracion_actual", "fiscal", "backups", "logs"}
    assert "fichero" in e["logs"]


def test_registrar_evento_emite_log(caplog):
    from src.utils import observabilidad as O
    with caplog.at_level(logging.INFO, logger="smart_manager.eventos"):
        O.registrar_evento("login", "acceso correcto", usuario="X")
        O.registrar_evento("fiscal", "registro emitido", nivel="info", serie="A")
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "[login] acceso correcto" in msgs and "usuario=X" in msgs
    assert "[fiscal] registro emitido" in msgs


def test_backup_emite_evento(db, monkeypatch, caplog):
    from src.db import backup as B
    monkeypatch.setattr("src.db.backup.shutil.which", lambda _e: None)   # camino lógico
    with caplog.at_level(logging.INFO, logger="smart_manager.eventos"):
        meta = B.crear_backup(motivo="test_obs")
    import os
    try:
        assert meta["resultado"] == "ok"
        assert any("[backup] backup creado" in r.getMessage() for r in caplog.records)
    finally:
        for f in (meta["ruta"], meta["ruta"][:-4] + ".json"):
            if os.path.exists(f):
                os.remove(f)


def test_diagnostico_texto(db):
    from src.utils import observabilidad as O
    txt = O.diagnostico_texto()
    assert "Diagnóstico Smart Manager AI" in txt
    assert "Base de datos:" in txt and "Migración:" in txt and "Fiscal:" in txt


def test_excepthook_global_instalado():
    """El logging global instala captura de excepciones no controladas."""
    import sys
    from src.utils import logger as L
    L.configurar_logging()
    L.instalar_captura_global()
    assert sys.excepthook is not sys.__excepthook__   # hook propio activo
