"""
F4.1.2 · Persistencia laboral RRHH (expediente del trabajador).

Migración 0017 (aplicar/revertir/reaplicar), CRUD de las 6 tablas, unicidad NIF por
empresa, aislamiento multiempresa, FK + cascada, y agregación de expediente.
"""

import pytest

pytestmark = pytest.mark.db

from src.rrhh.db import (ausencias as A, contratos as C, documentos as D,
                         empleados as E, nominas as N, vacaciones as V)


def _limpia(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rrhh_empleados WHERE id_empresa=%s", (emp,))  # cascada hijos
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _empleado(db, fab, **kw):
    emp = fab.empresa("RRHH EXP")
    fab.al_limpiar(lambda: _limpia(db, emp))
    defaults = dict(nombre="Juan", apellidos="Pérez", nif="12345678Z", salario_base=1200)
    defaults.update(kw)
    eid = E.crear_empleado(id_empresa=emp, **defaults)
    return emp, eid


# ── Migración ──────────────────────────────────────────────────────────────────
def test_tablas_existen(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SHOW TABLES LIKE 'rrhh_%'")
        nombres = {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}
    for t in ("rrhh_empleados", "rrhh_contratos", "rrhh_nominas", "rrhh_vacaciones",
              "rrhh_ausencias", "rrhh_documentos"):
        assert t in nombres


def test_migracion_reversible(db):
    from src.db.migrador import descubrir
    m = [x for x in descubrir() if x.version == "0017"][0]
    # FK_CHECKS=0: migraciones posteriores (0018 control horario, 0019 firma) añaden
    # tablas/columnas que dependen de 0017; revertir 0017 aislado no debe bloquearse.
    # Tras reaplicar 0017 se reaplican también las posteriores para restaurar el esquema
    # completo (idempotentes: CREATE/ADD COLUMN IF NOT EXISTS).
    posteriores = [x for x in descubrir() if x.version in ("0017", "0018", "0019")]
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        try:
            m.revertir(cur)
            cur.execute("SHOW TABLES LIKE 'rrhh_empleados'")
            ausente = cur.fetchall() == ()
            for mig in posteriores:        # 0017 → 0018 → 0019 (restaura todo)
                mig.aplicar(cur)
            conn.commit()
        finally:
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
            conn.commit()
        cur.execute("SHOW TABLES LIKE 'rrhh_documentos'")
        presente = cur.fetchall() != ()
        cur.execute("SHOW COLUMNS FROM rrhh_documentos LIKE 'estado_firma'")
        col_firma = cur.fetchall() != ()
    assert ausente and presente and col_firma


def test_indices_y_unicidad(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SHOW INDEX FROM rrhh_empleados WHERE Key_name='uq_emp_nif'")
        assert cur.fetchall(), "falta índice único uq_emp_nif"
        cur.execute("SHOW INDEX FROM rrhh_nominas WHERE Key_name='uq_nom_periodo'")
        assert cur.fetchall(), "falta índice único uq_nom_periodo"


# ── CRUD empleados + unicidad NIF ───────────────────────────────────────────────
def test_crud_empleado(db, fab):
    emp, eid = _empleado(db, fab)
    assert eid
    f = E.obtener_empleado(eid, emp)
    assert f["nombre"] == "Juan" and f["nif"] == "12345678Z" and f["estado"] == "activo"
    assert E.actualizar_empleado(eid, emp, puesto="Cajero", estado="suspendido")
    assert E.obtener_empleado(eid, emp)["puesto"] == "Cajero"
    assert E.obtener_por_nif("12345678Z", emp)["id"] == eid
    assert any(x["id"] == eid for x in E.listar_empleados(emp))


def test_nif_unico_por_empresa(db, fab):
    emp, eid = _empleado(db, fab)
    dup = E.crear_empleado(id_empresa=emp, nombre="Otro", nif="12345678Z")
    assert dup is None                       # NIF duplicado en la misma empresa → rechazado


def test_mismo_nif_distinta_empresa(db, fab):
    emp1, e1 = _empleado(db, fab)
    emp2 = fab.empresa("RRHH EXP 2")
    fab.al_limpiar(lambda: _limpia(db, emp2))
    e2 = E.crear_empleado(id_empresa=emp2, nombre="Juan", nif="12345678Z")
    assert e2 and e2 != e1                    # mismo NIF permitido en otra empresa


def test_aislamiento_multiempresa(db, fab):
    emp1, e1 = _empleado(db, fab)
    emp2 = fab.empresa("RRHH EXP B")
    fab.al_limpiar(lambda: _limpia(db, emp2))
    assert E.obtener_empleado(e1, emp2) is None        # no visible desde otra empresa
    assert all(x["id"] != e1 for x in E.listar_empleados(emp2))


# ── Historiales (CRUD) ──────────────────────────────────────────────────────────
def test_crud_historiales(db, fab):
    emp, eid = _empleado(db, fab)
    cid = C.crear_contrato(eid, emp, modalidad="INDEFINIDO", salario=1200, fecha_inicio="2026-01-01")
    nid = N.crear_nomina(eid, emp, anio=2026, mes=6, bruto=1200, neto=1000, irpf_pct=15)
    vid = V.crear_vacaciones(eid, emp, anio=2026, tipo="solicitud", dias=5)
    aid = A.crear_ausencia(eid, emp, tipo="permiso", dias=1, motivo="médico")
    did = D.crear_documento(eid, emp, tipo_doc="contrato", ref_documento="x.pdf")
    assert all([cid, nid, vid, aid, did])
    assert len(C.listar_contratos(eid, emp)) == 1
    assert len(N.listar_nominas(eid, emp)) == 1
    assert len(V.listar_vacaciones(eid, emp)) == 1
    assert len(A.listar_ausencias(eid, emp)) == 1
    assert len(D.listar_documentos(eid, emp)) == 1
    assert N.actualizar_nomina(nid, emp, neto=1010)
    assert N.obtener_nomina(nid, emp)["neto"] == 1010
    assert C.eliminar_contrato(cid, emp) and len(C.listar_contratos(eid, emp)) == 0


def test_nomina_periodo_unico(db, fab):
    emp, eid = _empleado(db, fab)
    assert N.crear_nomina(eid, emp, anio=2026, mes=6, bruto=1200)
    assert N.crear_nomina(eid, emp, anio=2026, mes=6, bruto=1300) is None   # período duplicado


# ── FK + cascada + expediente ───────────────────────────────────────────────────
def test_cascada_al_borrar_empleado(db, fab):
    emp, eid = _empleado(db, fab)
    C.crear_contrato(eid, emp, modalidad="TEMPORAL")
    N.crear_nomina(eid, emp, anio=2026, mes=1, bruto=1000)
    D.crear_documento(eid, emp, tipo_doc="nomina")
    assert E.eliminar_empleado(eid, emp)
    # los historiales se borran en cascada (FK ON DELETE CASCADE)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("rrhh_contratos", "rrhh_nominas", "rrhh_documentos"):
            cur.execute(f"SELECT COUNT(*) FROM {t} WHERE id_empleado=%s", (eid,))
            assert (cur.fetchone()[0] or 0) == 0, f"{t} no se borró en cascada"


def test_fk_rechaza_empleado_inexistente(db, fab):
    emp = fab.empresa("RRHH FK")
    fab.al_limpiar(lambda: _limpia(db, emp))
    # id_empleado inexistente → la FK debe impedir el insert (devuelve None por except)
    assert C.crear_contrato(999999999, emp, modalidad="INDEFINIDO") is None


def test_expediente_agrega_historiales(db, fab):
    emp, eid = _empleado(db, fab)
    C.crear_contrato(eid, emp, modalidad="INDEFINIDO")
    N.crear_nomina(eid, emp, anio=2026, mes=6, bruto=1200)
    V.crear_vacaciones(eid, emp, anio=2026, dias=2)
    A.crear_ausencia(eid, emp, tipo="permiso")
    D.crear_documento(eid, emp, tipo_doc="contrato")
    exp = E.expediente(eid, emp)
    assert exp["empleado"]["id"] == eid
    assert len(exp["contratos"]) == 1 and len(exp["nominas"]) == 1
    assert len(exp["vacaciones"]) == 1 and len(exp["ausencias"]) == 1
    assert len(exp["documentos"]) == 1
