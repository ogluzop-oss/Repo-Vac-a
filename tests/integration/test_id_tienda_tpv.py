"""Unificación de `id_tienda` a INT — grupo TPV (migr 0196), cierra la unificación (10/10).

- cierres_z: clave exacta de numeración por tienda → INT NOT NULL, central 'ALMC' → 0.
- tpv_tickets_aparcados: consulta null-safe (<=>) → INT NULL, sin tienda → NULL.
"""

import pytest

from src.services.tpv import cierre_z as CZ
from src.services.tpv import tpv_pro as TP

pytestmark = pytest.mark.db


def _raw(db, tabla, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT id_tienda FROM {tabla} WHERE id_empresa=%s ORDER BY id DESC LIMIT 1", (id_empresa,))
        r = cur.fetchone()
        return (r[0] if not isinstance(r, dict) else r["id_tienda"]) if r else "SIN_FILA"


def _limpia(db, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cierres_z WHERE id_empresa=%s", (id_empresa,))
        cur.execute("DELETE FROM tpv_tickets_aparcados WHERE id_empresa=%s", (id_empresa,))
        conn.commit()


def test_cierre_z_id_tienda_central(db, fab):
    emp = fab.empresa("EMP tpv A")
    fab.al_limpiar(lambda: _limpia(db, emp))

    r = CZ.generar_cierre_z("2026-05-10", 0.0, id_empresa=emp, id_tienda="ALMC", generar_pdf=False)
    assert r is not None
    assert _raw(db, "cierres_z", emp) == 0                     # 'ALMC' → 0

    # existe_cierre con '' (→0) localiza el mismo cierre (clave exacta coherente)
    assert CZ.existe_cierre("2026-05-10", emp, id_tienda="", caja=1) is not None
    # y regenerarlo con '' devuelve el mismo (duplicado), no crea otra fila
    r2 = CZ.generar_cierre_z("2026-05-10", 0.0, id_empresa=emp, id_tienda="", generar_pdf=False)
    assert r2 and r2.get("duplicado") is True


def test_tickets_aparcados_id_tienda(db, fab):
    emp = fab.empresa("EMP tpv B")
    fab.al_limpiar(lambda: _limpia(db, emp))

    t_almc = TP.aparcar_ticket([], id_empresa=emp, id_tienda="ALMC")   # → 0
    assert t_almc
    assert _raw(db, "tpv_tickets_aparcados", emp) == 0

    t_none = TP.aparcar_ticket([], id_empresa=emp, id_tienda=None)     # → NULL
    assert t_none
    assert _raw(db, "tpv_tickets_aparcados", emp) is None

    # filtrar por central (0) devuelve el ticket central (null-safe)
    refs = TP.tickets_aparcados(id_empresa=emp, id_tienda="ALMC")
    assert any(t["id"] == t_almc for t in refs)
