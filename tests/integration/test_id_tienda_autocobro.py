"""Unificación de `id_tienda` a INT — grupo Autocobro (migr 0194).

Logs por tienda con analítica agregada: tienda concreta = int (central 'ALMC' → 0), sin tienda = NULL
(todas, sin filtro). Verifica el guardado y que el filtro por tienda 0 (central) sí discrimina.
"""

import pytest

from src.services.tpv import autocobro_seguridad as SEG

pytestmark = pytest.mark.db


def _raw_tiendas(db, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_tienda FROM autocobro_incidencias WHERE id_empresa=%s ORDER BY id", (id_empresa,))
        return [(r[0] if not isinstance(r, dict) else r["id_tienda"]) for r in cur.fetchall()]


def _limpia(db, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM autocobro_incidencias WHERE id_empresa=%s", (id_empresa,))
        cur.execute("DELETE FROM autocobro_seguridad_log WHERE id_empresa=%s", (id_empresa,))
        conn.commit()


def test_id_tienda_convencion_int(db, fab):
    emp = fab.empresa("EMP autocobro A")
    fab.al_limpiar(lambda: _limpia(db, emp))

    assert SEG.registrar_incidencia("T1", "ART1", "Art 1", id_empresa=emp, id_tienda="ALMC") is True
    assert SEG.registrar_incidencia("T1", "ART2", "Art 2", id_empresa=emp, id_tienda=2) is True
    assert SEG.registrar_incidencia("T1", "ART3", "Art 3", id_empresa=emp, id_tienda="") is True

    assert _raw_tiendas(db, emp) == [0, 2, None]   # 'ALMC'→0, 2→2, ''→NULL (todas)


def test_analitica_filtra_por_tienda_central(db, fab):
    emp = fab.empresa("EMP autocobro B")
    fab.al_limpiar(lambda: _limpia(db, emp))

    SEG.registrar_incidencia("T1", "CENTRAL", "En central", id_empresa=emp, id_tienda="ALMC")  # →0
    SEG.registrar_incidencia("T1", "OTRA", "En tienda 2", id_empresa=emp, id_tienda=2)

    # filtrar por central (0) devuelve SOLO la de central (antes 'if tie:' con 0 no filtraba)
    cods_central = {r["codigo"] for r in SEG.articulos_conflictivos(id_empresa=emp, id_tienda="ALMC")}
    assert cods_central == {"CENTRAL"}
    # sin tienda → todas
    cods_todas = {r["codigo"] for r in SEG.articulos_conflictivos(id_empresa=emp)}
    assert cods_todas == {"CENTRAL", "OTRA"}
