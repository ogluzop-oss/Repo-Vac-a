"""Integración · motor de migraciones versionadas (C4.1)."""

import types

import pytest

pytestmark = pytest.mark.db


def _reset_tabla(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS schema_migraciones")
        conn.commit()


def test_descubre_baseline(db):
    from src.db import migrador
    versiones = [m.version for m in migrador.descubrir()]
    assert "0001" in versiones


def test_sella_baseline_en_bd_existente(db):
    from src.db import migrador
    _reset_tabla(db)
    res = migrador.aplicar_pendientes(backup=False)
    # La BD de pruebas ya tiene esquema (usuarios) -> baseline SE SELLA, no se ejecuta.
    assert "0001" in res["selladas"] and res["error"] is None
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT resultado, ejecutor, tenant, checksum FROM schema_migraciones WHERE version='0001'")
        resultado, ejecutor, tenant, checksum = cur.fetchone()
    assert resultado == "stamp" and ejecutor and tenant and checksum is not None


def test_idempotente(db):
    from src.db import migrador
    migrador.aplicar_pendientes(backup=False)
    res = migrador.aplicar_pendientes(backup=False)
    assert res["aplicadas"] == [] and res["selladas"] == []


def test_aplicar_y_revertir_migracion(db, monkeypatch):
    from src.db import migrador
    mod = types.ModuleType("m9999_tmp")
    mod.VERSION = "9999"
    mod.DESCRIPCION = "tabla temporal de prueba"
    mod.aplicar = lambda cur: cur.execute("CREATE TABLE IF NOT EXISTS _mig_tmp (id INT)")
    mod.revertir = lambda cur: cur.execute("DROP TABLE IF EXISTS _mig_tmp")
    mig = migrador._Migracion(mod)
    monkeypatch.setattr(migrador, "descubrir", lambda: [mig])
    try:
        res = migrador.aplicar_pendientes(backup=False)
        assert "9999" in res["aplicadas"]
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE '_mig_tmp'")
            assert cur.fetchone() is not None
            cur.execute("SELECT duracion_ms, resultado FROM schema_migraciones WHERE version='9999'")
            dur, resu = cur.fetchone()
            assert resu == "ok" and dur is not None
        # Revertir baja la 9999 (drop tabla + borra registro).
        rev = migrador.revertir("0001")
        assert "9999" in rev["revertidas"]
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE '_mig_tmp'")
            assert cur.fetchone() is None
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS _mig_tmp")
            cur.execute("DELETE FROM schema_migraciones WHERE version='9999'")
            conn.commit()


def test_init_db_integra_runner(db):
    """init_db() (arranque) garantiza esquema y registra/sella la baseline."""
    _reset_tabla(db)
    assert db.init_db() is True
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT resultado FROM schema_migraciones WHERE version='0001'")
        fila = cur.fetchone()
    assert fila is not None and fila[0] in ("stamp", "ok")


def test_backup_genera_fichero_y_metadatos(db):
    import json
    import os
    from src.db import backup
    meta = backup.crear_backup(version_objetivo="0001", motivo="test_backup")
    try:
        assert meta["resultado"] == "ok" and meta["metodo"] in ("mysqldump", "export_logico")
        assert os.path.exists(meta["ruta"])
        side = meta["ruta"][:-4] + ".json"
        assert os.path.exists(side)
        with open(side, encoding="utf-8") as f:
            d = json.load(f)
        assert d["version_objetivo"] == "0001" and d["db"].endswith("_test")
    finally:
        for f in (meta["ruta"], meta["ruta"][:-4] + ".json"):
            if os.path.exists(f):
                os.remove(f)
