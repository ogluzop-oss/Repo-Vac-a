"""Unificación de `id_tienda` a INT — piloto `precio_reglas` (migr 0192).

Verifica la convención unificada: None/'' = TODAS las tiendas (NULL en BD); código central ('ALMC') → 0;
tienda concreta → su entero; y que el listado por tienda incluye las reglas globales (NULL).
"""

import pytest

from src.services.precio_dinamico import reglas as R

pytestmark = pytest.mark.db


def _id_tienda_bruto(db, id_regla):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_tienda FROM precio_reglas WHERE id=%s", (id_regla,))
        r = cur.fetchone()
        return (r[0] if not isinstance(r, dict) else r["id_tienda"]) if r else "SIN_FILA"


def test_convencion_id_tienda_int(db, fab):
    emp = fab.empresa("EMP idtienda")
    fab.al_limpiar(lambda: _borra_reglas(db, emp))

    r_global = R.crear_regla("Global", "stock", {}, id_tienda=None, id_empresa=emp)
    r_tienda = R.crear_regla("Tienda2", "stock", {}, id_tienda=2, id_empresa=emp)
    r_almc = R.crear_regla("Central", "stock", {}, id_tienda="ALMC", id_empresa=emp)
    assert all([r_global, r_tienda, r_almc])

    assert _id_tienda_bruto(db, r_global) is None      # None/'' → NULL (todas)
    assert _id_tienda_bruto(db, r_tienda) == 2          # tienda concreta → int
    assert _id_tienda_bruto(db, r_almc) == 0            # 'ALMC' (central) → 0


def test_listar_por_tienda_incluye_globales(db, fab):
    emp = fab.empresa("EMP idtienda2")
    fab.al_limpiar(lambda: _borra_reglas(db, emp))

    R.crear_regla("Global", "stock", {}, id_tienda=None, id_empresa=emp)
    R.crear_regla("Solo T2", "stock", {}, id_tienda=2, id_empresa=emp)
    R.crear_regla("Solo T3", "stock", {}, id_tienda=3, id_empresa=emp)

    nombres = {r["nombre"] for r in R.listar_reglas(id_empresa=emp, id_tienda=2)}
    assert "Solo T2" in nombres        # la de su tienda
    assert "Global" in nombres         # + las globales (NULL)
    assert "Solo T3" not in nombres     # no las de otras tiendas


def test_actualizar_coacciona_id_tienda(db, fab):
    emp = fab.empresa("EMP idtienda3")
    fab.al_limpiar(lambda: _borra_reglas(db, emp))

    rid = R.crear_regla("R", "stock", {}, id_tienda=2, id_empresa=emp)
    assert R.actualizar_regla(rid, id_empresa=emp, id_tienda="") is True
    assert _id_tienda_bruto(db, rid) is None            # '' → NULL (todas)


def _borra_reglas(db, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM precio_reglas WHERE id_empresa=%s", (id_empresa,))
        conn.commit()
