"""
SaaS — licenciamiento, enforcement de planes/límites, suscripciones, billing, usuarios
multiempresa, branding, backup por tenant, métricas y compatibilidad legacy.
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.services.saas import (planes as P, licensing as L, suscripciones as S,
                               multiempresa as ME, branding as BR, backup_tenant as BT, metricas as MT)


@pytest.fixture(autouse=True)
def _planes():
    P.sincronizar_planes()
    yield


def _emp():
    return str(uuid.uuid4())


def _limpia(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("empresa_licencia", "historico_licencias", "eventos_licencia", "suscripciones",
                  "facturas_saas", "pagos_saas", "empresa_branding"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        conn.commit()


# ── Planes ────────────────────────────────────────────────────────────────────
def test_planes_sembrados(db):
    assert P.sincronizar_planes() == 3
    assert "bi" in P.plan("PLUS")["modulos"] and "bi" not in P.plan("BASIC")["modulos"]
    assert P.plan("PRO")["limites"]["max_usuarios"] >= 9999


# ── Enforcement módulo + compatibilidad legacy ───────────────────────────────
def test_enforcement_modulo(db):
    emp = _emp()
    try:
        # Sin licencia → legacy, todo permitido
        assert L.modulo_habilitado("bi", emp) is True
        assert L.validar_operacion(modulo="bi", id_empresa=emp) is True
        L.asignar_plan(emp, "BASIC")
        assert L.modulo_habilitado("ventas", emp) is True
        assert L.modulo_habilitado("bi", emp) is False
        with pytest.raises(L.LicenciaError):
            L.validar_operacion(modulo="bi", id_empresa=emp)
        L.asignar_plan(emp, "PRO")
        assert L.modulo_habilitado("bi", emp) is True
    finally:
        _limpia(db, emp)


# ── Límites ───────────────────────────────────────────────────────────────────
def test_limite_usuarios(db):
    emp = _emp()
    try:
        L.asignar_plan(emp, "BASIC")   # max_usuarios=3
        info = L.limite_disponible("max_usuarios", emp)
        assert info["limite"] == 3 and info["ok"] is True
    finally:
        _limpia(db, emp)


# ── Suscripción + billing simulado ───────────────────────────────────────────
def test_suscripcion_y_billing(db):
    emp = _emp()
    try:
        sid = S.crear(emp, "PLUS", ciclo="mensual", prueba=False, proveedor="simulado")
        assert sid
        lic = L.licencia_activa(emp)
        assert lic["codigo_plan"] == "PLUS" and lic["estado"] == "activa"
        # se emitió factura y pago (simulado → pagado)
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM facturas_saas WHERE id_empresa=%s AND estado='pagada'", (emp,))
            assert cur.fetchone()[0] >= 1
            cur.execute("SELECT COUNT(*) FROM pagos_saas WHERE id_empresa=%s AND estado='pagado'", (emp,))
            assert cur.fetchone()[0] >= 1
    finally:
        _limpia(db, emp)


def test_upgrade_downgrade_cancelar(db):
    emp = _emp()
    try:
        S.crear(emp, "BASIC", prueba=True)
        S.cambiar_plan(emp, "PRO")
        assert L.licencia_activa(emp)["codigo_plan"] == "PRO"
        S.cambiar_plan(emp, "PLUS")
        assert L.licencia_activa(emp)["codigo_plan"] == "PLUS"
        S.cancelar(emp)
        assert L.licencia_activa(emp)["estado"] == "cancelada"
        assert L.modulo_habilitado("ventas", emp) is False   # cancelada → bloquea
    finally:
        _limpia(db, emp)


# ── Usuarios multiempresa ─────────────────────────────────────────────────────
def test_usuarios_multiempresa(db):
    e1, e2 = _emp(), _emp()
    uid = 770001
    try:
        ME.vincular(uid, e1, rol="ADMINISTRADOR", tipo_relacion="consultor")
        ME.vincular(uid, e2, rol="GERENTE", tipo_relacion="asesoria")
        emps = {x["id_empresa"]: x["rol"] for x in ME.empresas_de_usuario(uid)}
        assert emps.get(e1) == "ADMINISTRADOR" and emps.get(e2) == "GERENTE"
        assert ME.rol_en_empresa(uid, e2) == "GERENTE"
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM usuarios_empresas WHERE id_usuario=%s", (uid,))
            conn.commit()


# ── Branding ──────────────────────────────────────────────────────────────────
def test_branding(db):
    emp = _emp()
    try:
        BR.set_branding(emp, nombre_comercial="ACME Retail", color_primario="#00FFC6",
                        pie_documental="Gracias por su confianza")
        b = BR.obtener_branding(emp)
        assert b["nombre_comercial"] == "ACME Retail" and b["color_primario"] == "#00FFC6"
    finally:
        _limpia(db, emp)


# ── Backup por tenant ─────────────────────────────────────────────────────────
def test_backup_tenant(db):
    import os
    emp = _emp()
    try:
        L.asignar_plan(emp, "BASIC")   # genera fila en empresa_licencia (con id_empresa)
        r = BT.exportar_empresa(emp)
        assert r["ruta"] and os.path.exists(r["ruta"])
        import json
        with open(r["ruta"], encoding="utf-8") as f:
            data = json.load(f)
        assert data["id_empresa"] == emp and "empresa_licencia" in data["datos"]
        os.remove(r["ruta"])
    finally:
        _limpia(db, emp)


# ── Métricas SaaS ─────────────────────────────────────────────────────────────
def test_metricas(db):
    emp = _emp()
    try:
        S.crear(emp, "PLUS", prueba=False, proveedor="simulado")
        m = MT.resumen()
        assert m["empresas_activas"] >= 1 and m["mrr"] >= 0 and m["arr"] == round(m["mrr"] * 12, 2)
        cons = MT.consumo_empresa(emp)
        assert "ventas" in cons and "usuarios" in cons
    finally:
        _limpia(db, emp)
