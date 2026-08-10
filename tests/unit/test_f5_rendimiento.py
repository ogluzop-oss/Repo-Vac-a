"""
Tests Etapa F · Fase F5: rendimiento (índices).

Verifica que la migración 0151 crea los índices `id_empresa` en las tablas hot sin índice (aditiva,
idempotente, reversible) y que la consulta operacional (F1/F3) sobre `scheduler_ejecuciones` usa el
índice (deja de ser full-scan). Los índices NO cambian el comportamiento funcional: solo aceleran.
"""

import pytest

pytestmark = pytest.mark.db


def _indices_f5(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS "
                    "WHERE TABLE_SCHEMA=DATABASE() AND INDEX_NAME LIKE 'idx_f5_%'")
        return {r[0] if not isinstance(r, dict) else list(r.values())[0] for r in cur.fetchall()}


def test_migracion_0151_registrada():
    import importlib
    from src.database.migraciones import MODULOS
    assert "0151_indices_rendimiento" in MODULOS
    m = importlib.import_module("src.database.migraciones.0151_indices_rendimiento")
    assert m.REVERSIBLE is True and hasattr(m, "revertir") and hasattr(m, "aplicar")


def test_indices_creados(db):
    idx = _indices_f5(db)
    # al menos los índices clave (scheduler_ejecuciones compuesto + varios hot)
    assert "idx_f5_sch_ej_emp" in idx
    assert len(idx) >= 8


def test_consulta_operacional_usa_indice(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("EXPLAIN SELECT COUNT(*) FROM scheduler_ejecuciones "
                    "WHERE id_empresa='X' AND estado='fallido'")
        cols = [d[0] for d in cur.description]
        fila = cur.fetchone()
        d = fila if isinstance(fila, dict) else dict(zip(cols, fila))
    assert d.get("key") == "idx_f5_sch_ej_emp"       # usa el índice nuevo
    assert d.get("type") != "ALL"                     # ya no es full-scan


def test_comportamiento_preservado(db):
    # El índice no cambia el resultado: el conteo por tenant sigue siendo correcto (0 en tenant nuevo).
    from src.services.observabilidad import operacional
    snap = operacional.snapshot("T-F5-NUEVO")
    assert snap["scheduler"].get("ejecuciones_fallidas") == 0
