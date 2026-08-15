"""Unificación de `id_tienda` a INT — grupo ESL (migr 0193).

ESL clavea (empresa, tienda) de forma exacta; no hay "todas las tiendas". Verifica que la config y las
etiquetas se guardan/leen con `id_tienda` entero (código 'ALMC'/sin contexto → 0; tienda concreta → int).
"""

import pytest

from src.services.esl import config as CFG
from src.services.esl import registro as REG

pytestmark = pytest.mark.db


def _raw(db, tabla, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT id_tienda FROM {tabla} WHERE id_empresa=%s LIMIT 1", (id_empresa,))
        r = cur.fetchone()
        return (r[0] if not isinstance(r, dict) else r["id_tienda"]) if r else "SIN_FILA"


def _limpia(db, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM esl_labels WHERE id_empresa=%s", (id_empresa,))
        cur.execute("DELETE FROM esl_config WHERE id_empresa=%s", (id_empresa,))
        conn.commit()


def test_config_esl_id_tienda_int(db, fab):
    emp = fab.empresa("EMP esl A")
    fab.al_limpiar(lambda: _limpia(db, emp))

    # 'ALMC' (central) → 0; roundtrip por obtener_config
    assert CFG.guardar_config(proveedor="simulado", id_empresa=emp, id_tienda="ALMC") is True
    assert _raw(db, "esl_config", emp) == 0
    cfg = CFG.obtener_config(id_empresa=emp, id_tienda="ALMC")
    assert cfg and cfg.get("proveedor") == "simulado"


def test_config_esl_tienda_concreta(db, fab):
    emp = fab.empresa("EMP esl B")
    fab.al_limpiar(lambda: _limpia(db, emp))

    assert CFG.guardar_config(proveedor="simulado", id_empresa=emp, id_tienda=2) is True
    assert _raw(db, "esl_config", emp) == 2


def test_labels_esl_vincular_y_listar(db, fab):
    emp = fab.empresa("EMP esl C")
    fab.al_limpiar(lambda: _limpia(db, emp))
    cod = fab.articulo(id_empresa=emp)   # vincular valida que el artículo exista

    assert REG.vincular(cod, "LBL-1", id_empresa=emp, id_tienda=2) is not None
    assert _raw(db, "esl_labels", emp) == 2
    etiquetas = REG.listar(id_empresa=emp, id_tienda=2)
    assert any(l.get("label_id") == "LBL-1" for l in etiquetas)
