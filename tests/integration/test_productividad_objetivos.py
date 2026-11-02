"""
Fase Productividad · Objetivos versionados (centro fijo / empleado dinámico-hora), facturación en
vivo y campañas paralelas. BD real.
"""

import datetime as _dt
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant
from src.services.productividad import campanas as C
from src.services.productividad import facturacion as F
from src.services.productividad import objetivos as O

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


def _min_tienda(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT MIN(id) FROM tiendas WHERE id_empresa=%s", (E,))
        r = cur.fetchone()
        return r[0] if not isinstance(r, dict) else list(r.values())[0]


# ── Objetivos de centro (fijo, versionado) ───────────────────────────────────
def test_fijar_y_leer_objetivo_centro(fab, db):
    cod_centro = "PRODTEST-" + uuid.uuid4().hex[:6]
    oid = O.fijar_objetivo_centro(cod_centro, "mensual", 5000, E, creado_por_id=1)
    fab.al_limpiar(lambda: _del(db, "productividad_objetivos", "id", oid))
    assert oid is not None
    obj = O.objetivo_en_fecha("centro", "mensual", E, centro_codigo=cod_centro)
    assert obj is not None and obj["valor"] == 5000.0


def test_reemplazar_objetivo_centro_cierra_version_anterior_y_preserva_historico(fab, db):
    """Editar el objetivo NO borra el histórico: una fecha de referencia pasada sigue resolviendo
    a la versión que estaba vigente entonces."""
    cod_centro = "PRODTEST-" + uuid.uuid4().hex[:6]
    hace_60 = _dt.date.today() - _dt.timedelta(days=60)
    hace_30 = _dt.date.today() - _dt.timedelta(days=30)
    oid1 = O.fijar_objetivo_centro(cod_centro, "mensual", 1000, E, vigente_desde=hace_60)
    oid2 = O.fijar_objetivo_centro(cod_centro, "mensual", 2000, E, vigente_desde=hace_30)
    fab.al_limpiar(lambda: _del(db, "productividad_objetivos", "id", oid1))
    fab.al_limpiar(lambda: _del(db, "productividad_objetivos", "id", oid2))

    historico = O.objetivo_en_fecha("centro", "mensual", E, hace_60 + _dt.timedelta(days=5),
                                     centro_codigo=cod_centro)
    actual = O.objetivo_en_fecha("centro", "mensual", E, centro_codigo=cod_centro)
    assert historico["valor"] == 1000.0
    assert actual["valor"] == 2000.0


def test_objetivos_obligatorios_completos(fab, db):
    cod_centro = "PRODTEST-" + uuid.uuid4().hex[:6]
    incompleto = O.objetivos_obligatorios_completos("centro", E, centro_codigo=cod_centro)
    assert incompleto == {"mensual": False, "semestral": False, "anual": False}

    ids = []
    for periodo, valor in (("mensual", 100), ("semestral", 600), ("anual", 1200)):
        oid = O.fijar_objetivo_centro(cod_centro, periodo, valor, E)
        ids.append(oid)
        fab.al_limpiar(lambda oid=oid: _del(db, "productividad_objetivos", "id", oid))

    completo = O.objetivos_obligatorios_completos("centro", E, centro_codigo=cod_centro)
    assert completo == {"mensual": True, "semestral": True, "anual": True}


# ── Objetivo dinámico de empleado (tarifa/hora × horas trabajadas de Fichajes) ──
def test_objetivo_dinamico_empleado_usa_horas_de_fichajes(fab, db):
    usuario_id = 9001
    oid = O.fijar_objetivo_empleado(usuario_id, "diario", 20, E)  # 20€/hora
    fab.al_limpiar(lambda: _del(db, "productividad_objetivos", "id", oid))

    hoy = _dt.date.today()
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO fichajes (id_empresa, usuario_id, nombre_empleado, entrada, salida, "
            "duracion_segundos) VALUES (%s,%s,%s,%s,%s,%s)",
            (E, usuario_id, "Test Productividad", f"{hoy} 08:00:00", f"{hoy} 11:00:00", 3 * 3600))
        fid = cur.lastrowid
        conn.commit()
    fab.al_limpiar(lambda: _del(db, "fichajes", "id", fid))

    r = O.objetivo_dinamico_empleado(usuario_id, "diario", E)
    assert r["valor_hora"] == 20.0
    assert r["horas_trabajadas"] == 3.0
    assert r["objetivo_calculado"] == 60.0


def test_objetivo_dinamico_sin_objetivo_fijado_es_honestamente_cero(fab, db):
    r = O.objetivo_dinamico_empleado(999999, "mensual", E)
    assert r["valor_hora"] == 0.0 and r["objetivo_calculado"] == 0.0


# ── Facturación en vivo ───────────────────────────────────────────────────────
def test_facturado_centro_suma_ventas_del_rango(fab, db):
    from src.db.conexion import registrar_venta_con_items
    cod = _art(fab, db, stock_tienda=20)
    tid = _min_tienda(db)
    with contexto_tenant(E, tid):
        vid = registrar_venta_con_items(
            [{"codigo_articulo": cod, "cantidad": 2, "precio_unitario": 15}])
    fab.al_limpiar(lambda: _del(db, "venta_items", "venta_id", vid))
    hoy = _dt.date.today()
    total = F.facturado_centro(tid, hoy, hoy, E)
    assert total >= 30.0


def test_facturado_empleado_usa_id_usuario_fiable(fab, db):
    from src.db.conexion import registrar_venta_con_items
    cod = _art(fab, db, stock_tienda=20)
    with contexto_tenant(E, None):
        vid = registrar_venta_con_items(
            [{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 50}], id_usuario=9002)
    fab.al_limpiar(lambda: _del(db, "venta_items", "venta_id", vid))
    hoy = _dt.date.today()
    assert F.facturado_empleado(9002, hoy, hoy, E) >= 50.0
    assert F.facturado_empleado(9003, hoy, hoy, E) == 0.0  # otro empleado: nunca se cruza


def test_facturado_sin_id_devuelve_cero_honesto():
    hoy = _dt.date.today()
    assert F.facturado_centro(None, hoy, hoy, E) == 0.0
    assert F.facturado_empleado(None, hoy, hoy, E) == 0.0


# ── Campañas (paralelas a los objetivos ordinarios) ─────────────────────────
def test_campana_crud_y_objetivo_centro(fab, db):
    cid = C.crear_campana("Campaña Test", _dt.date.today() - _dt.timedelta(days=1),
                          _dt.date.today() + _dt.timedelta(days=5), E, creado_por_id=1)
    fab.al_limpiar(lambda: _del(db, "productividad_campanas", "id", cid))
    assert cid is not None
    assert any(c["id"] == cid for c in C.listar_campanas(E))

    cod_centro = "PRODTEST-" + uuid.uuid4().hex[:6]
    oid = C.fijar_objetivo_campana(cid, "centro", 999, E, centro_codigo=cod_centro)
    fab.al_limpiar(lambda: _del(db, "productividad_campana_objetivos", "id", oid))
    obj = C.objetivo_campana(cid, "centro", centro_codigo=cod_centro)
    assert obj["valor"] == 999.0

    # Editar reemplaza EN SITIO (no versiona) — mismo id, nuevo valor.
    oid2 = C.fijar_objetivo_campana(cid, "centro", 1500, E, centro_codigo=cod_centro)
    assert oid2 == oid
    assert C.objetivo_campana(cid, "centro", centro_codigo=cod_centro)["valor"] == 1500.0


def test_campana_es_paralela_no_sustituye_objetivo_ordinario(fab, db):
    """El objetivo ORDINARIO de un centro y su objetivo de CAMPAÑA conviven — consultar uno no
    afecta al otro (dos barras de progreso distintas y simultáneas, pedido explícito)."""
    cod_centro = "PRODTEST-" + uuid.uuid4().hex[:6]
    oid_ord = O.fijar_objetivo_centro(cod_centro, "mensual", 3000, E)
    fab.al_limpiar(lambda: _del(db, "productividad_objetivos", "id", oid_ord))

    cid = C.crear_campana("Campaña Paralela", _dt.date.today(),
                          _dt.date.today() + _dt.timedelta(days=10), E)
    fab.al_limpiar(lambda: _del(db, "productividad_campanas", "id", cid))
    oid_camp = C.fijar_objetivo_campana(cid, "centro", 777, E, centro_codigo=cod_centro)
    fab.al_limpiar(lambda: _del(db, "productividad_campana_objetivos", "id", oid_camp))

    assert O.objetivo_en_fecha("centro", "mensual", E, centro_codigo=cod_centro)["valor"] == 3000.0
    assert C.objetivo_campana(cid, "centro", centro_codigo=cod_centro)["valor"] == 777.0


def test_progreso_campana_empleado_dinamico(fab, db):
    usuario_id = 9004
    cid = C.crear_campana("Campaña Empleado", _dt.date.today() - _dt.timedelta(days=2),
                          _dt.date.today() + _dt.timedelta(days=2), E)
    fab.al_limpiar(lambda: _del(db, "productividad_campanas", "id", cid))
    oid = C.fijar_objetivo_campana(cid, "empleado", 10, E, usuario_id=usuario_id)  # 10€/hora
    fab.al_limpiar(lambda: _del(db, "productividad_campana_objetivos", "id", oid))

    hoy = _dt.date.today()
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO fichajes (id_empresa, usuario_id, nombre_empleado, entrada, salida, "
            "duracion_segundos) VALUES (%s,%s,%s,%s,%s,%s)",
            (E, usuario_id, "Test Campana", f"{hoy} 09:00:00", f"{hoy} 13:00:00", 4 * 3600))
        fid = cur.lastrowid
        conn.commit()
    fab.al_limpiar(lambda: _del(db, "fichajes", "id", fid))

    r = C.progreso_campana_empleado(cid, usuario_id, E)
    assert r["valor_hora"] == 10.0 and r["horas_trabajadas"] == 4.0
    assert r["objetivo"] == 40.0
