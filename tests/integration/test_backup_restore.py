"""E1.3 · Backup y restauración verificados (creación + restore + integridad)."""

import pytest

pytestmark = pytest.mark.db

_RESTORE_DB = "smart_manager_restore_test"   # BD separada (no toca la de trabajo)
_PROBE = "_backup_probe_e13"
_MARCA = "E1_3_PROBE_OK"


def _exec(db, sql, params=(), database=None):
    import pymysql
    from src.db.conexion import DB_CONFIG
    cfg = dict(DB_CONFIG)                       # BD de trabajo por defecto
    if database:
        cfg["database"] = database
    elif "DROP DATABASE" in sql or "CREATE DATABASE" in sql:
        cfg.pop("database", None)              # operaciones a nivel servidor
    conn = pymysql.connect(**cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            fila = cur.fetchone() if cur.description else None
        conn.commit()
        return fila
    finally:
        conn.close()


@pytest.fixture
def _forzar_portable(monkeypatch):
    """Fuerza el camino portable (export lógico + restore PyMySQL) ignorando los
    clientes mysqldump/mysql del sistema → test determinista en cualquier entorno."""
    monkeypatch.setattr("src.db.backup.shutil.which", lambda _exe: None)


def test_crear_backup_logico_genera_fichero_y_metadatos(db, _forzar_portable):
    from src.db import backup as B
    meta = B.crear_backup(motivo="test_e13")
    import os
    assert meta["resultado"] == "ok" and meta["metodo"] == "export_logico"
    assert os.path.exists(meta["ruta"]) and os.path.exists(meta["ruta"][:-4] + ".json")
    assert meta["tablas"] and "usuarios" in meta["tablas"]
    assert any(b["ruta"] == meta["ruta"] for b in B.listar_backups())
    os.remove(meta["ruta"]); os.remove(meta["ruta"][:-4] + ".json")


def test_restauracion_recupera_datos(db, _forzar_portable):
    """Crea una marca, respalda, restaura en BD separada y verifica integridad."""
    from src.db import backup as B
    import os
    # 1) Marca conocida en la BD de trabajo.
    _exec(db, f"CREATE TABLE IF NOT EXISTS {_PROBE} (id INT PRIMARY KEY, marca VARCHAR(50))")
    _exec(db, f"REPLACE INTO {_PROBE} (id, marca) VALUES (1, %s)", (_MARCA,))
    try:
        # 2) Backup (export lógico).
        meta = B.crear_backup(motivo="test_e13_restore")
        assert meta["resultado"] == "ok"
        # 3) Restauración en una BD SEPARADA.
        _exec(db, f"DROP DATABASE IF EXISTS `{_RESTORE_DB}`")
        res = B.restaurar_backup(meta["ruta"], db=_RESTORE_DB)
        assert res["resultado"] == "ok" and res["metodo"] == "pymysql"
        # 4) Integridad: la marca existe en la BD restaurada.
        fila = _exec(db, f"SELECT marca FROM {_PROBE} WHERE id=1", database=_RESTORE_DB)
        assert fila and fila[0] == _MARCA
        # …y otras tablas del producto también se restauraron.
        n = _exec(db, "SELECT COUNT(*) FROM empresas", database=_RESTORE_DB)
        assert n and n[0] >= 1
    finally:
        _exec(db, f"DROP DATABASE IF EXISTS `{_RESTORE_DB}`")
        _exec(db, f"DROP TABLE IF EXISTS {_PROBE}")
        for f in (meta["ruta"], meta["ruta"][:-4] + ".json"):
            if os.path.exists(f):
                os.remove(f)


def test_restaurar_backup_inexistente(db):
    from src.db import backup as B
    res = B.restaurar_backup("ruta/que/no/existe.sql")
    assert res["resultado"] == "error" and "inexistente" in res.get("error", "")
