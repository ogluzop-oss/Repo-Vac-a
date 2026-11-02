"""
Fase Productividad · Fase 1 (verificación de cableado venta→empleado/centro).

`registrar_venta_con_items` acepta ahora `id_usuario` (migr. 0294, columna NUEVA y limpia
`ventas.id_usuario`), distinto del legado `empleado` (VARCHAR, histórico/display). Estos tests
confirman que la venta queda correctamente atribuida al empleado REAL (no inventada, no
heredada del legado) y que el selector de login por nombre del TPV (`validar_login_empleado`)
está aislado por empresa (antes buscaba el nombre en TODA la tabla `usuarios`, sin filtrar
`id_empresa` — un empleado de otra compañía con el mismo nombre podía autenticar como si fuera
de la empresa activa).
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant

E = EMPRESA_DEFAULT_ID


def _del(db, tabla, col, val):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(f"DELETE FROM {tabla} WHERE {col}=%s", (val,))
        conn.commit()


def _art(fab, db, **kw):
    cod = fab.articulo(**kw)

    def _l():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("stock_almacen", "lotes", "movimientos_stock", "venta_items"):
                cur.execute(f"DELETE FROM {t} WHERE codigo_articulo=%s", (cod,))
            conn.commit()

    fab.al_limpiar(_l)
    return cod


def test_registrar_venta_con_items_persiste_id_usuario(fab, db):
    from src.db.conexion import registrar_venta_con_items
    cod = _art(fab, db, stock_tienda=20)
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items(
            [{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 10}],
            id_usuario=777,
        )
    fab.al_limpiar(lambda: _del(db, "venta_items", "venta_id", vid))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_usuario FROM ventas WHERE id=%s", (vid,))
        r = cur.fetchone()
    valor = r[0] if not isinstance(r, dict) else r["id_usuario"]
    assert int(valor) == 777


def test_registrar_venta_sin_id_usuario_queda_null_honesto(fab, db):
    """Si no se indica (autocobro/online), nunca se inventa una atribución — queda NULL."""
    from src.db.conexion import registrar_venta_con_items
    cod = _art(fab, db, stock_tienda=20)
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items(
            [{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 10}],
        )
    fab.al_limpiar(lambda: _del(db, "venta_items", "venta_id", vid))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_usuario FROM ventas WHERE id=%s", (vid,))
        r = cur.fetchone()
    valor = r[0] if not isinstance(r, dict) else r["id_usuario"]
    assert valor is None


def test_validar_login_empleado_aislado_por_empresa(fab, db):
    """Dos empresas con un empleado de MISMO nombre y PIN distinto: autenticar en la empresa A
    no debe poder devolver nunca al empleado de la empresa B (antes del fix, la búsqueda por
    nombre no filtraba `id_empresa` y probaba contraseñas de ambos indistintamente)."""
    from src.db.usuario import validar_login_empleado
    from src.seguridad import passwords as _pw

    nombre = "PRODTEST-" + uuid.uuid4().hex[:6]
    emp_b = fab.empresa("PRODUCTIVIDAD B")
    fab.al_limpiar(lambda: _del(db, "empresas", "id_empresa", emp_b))

    hash_a = _pw.hash_password("pinA123")
    hash_b = _pw.hash_password("pinB456")
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO usuarios (nombre, password, perfil, id_empresa) "
            "VALUES (%s,%s,'OPERARIO',%s)", (nombre, hash_a, E))
        id_a = cur.lastrowid
        cur.execute(
            "INSERT INTO usuarios (nombre, password, perfil, id_empresa) "
            "VALUES (%s,%s,'OPERARIO',%s)", (nombre, hash_b, emp_b))
        id_b = cur.lastrowid
        conn.commit()
    fab.al_limpiar(lambda: _del(db, "usuarios", "id", id_a))
    fab.al_limpiar(lambda: _del(db, "usuarios", "id", id_b))

    with contexto_tenant(E, None):
        r = validar_login_empleado(nombre, "pinB456")
    assert r is None or r.get("id") != id_b
