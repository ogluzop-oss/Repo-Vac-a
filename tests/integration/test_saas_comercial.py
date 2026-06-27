"""
SaaS comercializable — enforcement real, bloqueo por impago, billing webhook→licencia, dunning,
login multiempresa, restore tenant, branding real, facturas PDF, hardening aislamiento.
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant
from src.services.saas import (planes as P, licensing as L, suscripciones as S, enforcement as EN,
                               multiempresa as ME, backup_tenant as BT, branding as BR,
                               facturas as FAC, dunning as DUN, aislamiento as AIS)
from src.services.saas.billing import webhooks as WH


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


# ── P0.1 Enforcement real (módulo) ───────────────────────────────────────────
def test_enforcement_modulo_real(db):
    emp = _emp()
    try:
        # legacy → permitido
        assert EN.acceso_modulo("bi", emp)[0] is True
        L.asignar_plan(emp, "BASIC")
        assert EN.acceso_modulo("ventas", emp)[0] is True
        assert EN.acceso_modulo("bi", emp)[0] is False        # BI no en BASIC
        with pytest.raises(L.LicenciaError):
            EN.exigir_modulo("bi", emp)
        L.asignar_plan(emp, "PRO")
        assert EN.acceso_modulo("bi", emp)[0] is True
    finally:
        _limpia(db, emp)


def test_enforcement_cableado_en_servicio(db):
    # El gate está realmente cableado: bi.dashboard.panel lo invoca.
    from src.services.bi import dashboard as D
    emp = _emp()
    try:
        L.asignar_plan(emp, "BASIC")          # sin BI
        with pytest.raises(L.LicenciaError):
            D.panel(emp)                       # ← enforcement real en el servicio
        L.asignar_plan(emp, "PRO")
        d = D.panel(emp)
        assert "secciones" in d
    finally:
        _limpia(db, emp)


# ── P0.3 Bloqueo por impago ──────────────────────────────────────────────────
def test_bloqueo_por_impago(db):
    emp = _emp()
    try:
        L.asignar_plan(emp, "PRO", estado="activa")
        assert EN.nivel_acceso(emp) == "normal"
        L.asignar_plan(emp, "PRO", estado="suspendida")
        assert EN.nivel_acceso(emp) == "lectura"
        L.asignar_plan(emp, "PRO", estado="cancelada")
        assert EN.nivel_acceso(emp) == "bloqueado"
        # cancelada → todo bloqueado salvo portal SaaS
        assert EN.acceso_modulo("ventas", emp)[0] is False
        assert EN.acceso_modulo("saas", emp)[0] is True
    finally:
        _limpia(db, emp)


# ── P0.4 Billing webhook → licencia ──────────────────────────────────────────
def test_billing_webhook_sincroniza_licencia(db):
    emp = _emp()
    try:
        S.crear(emp, "PLUS", prueba=False, proveedor="simulado")
        WH.procesar_evento("invoice.payment_failed", {"id_empresa": emp})
        assert L.licencia_activa(emp)["estado"] == "suspendida"
        WH.procesar_evento("invoice.paid", {"id_empresa": emp})
        assert L.licencia_activa(emp)["estado"] == "activa"
        WH.procesar_evento("customer.subscription.deleted", {"id_empresa": emp})
        assert L.licencia_activa(emp)["estado"] == "cancelada"
    finally:
        _limpia(db, emp)


# ── P0.5 Dunning ──────────────────────────────────────────────────────────────
def test_dunning(db):
    import datetime as dt
    emp = _emp()
    try:
        sid = S.crear(emp, "PLUS", prueba=False, proveedor="simulado")
        # fuerza proximo_cobro vencido hace 8 días → suspensión
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE suscripciones SET estado='activa', proximo_cobro=%s WHERE id_empresa=%s",
                        ((dt.date.today() - dt.timedelta(days=8)).isoformat(), emp))
            conn.commit()
        r = DUN.procesar_empresa(emp)
        assert r["accion"] == "suspendida"
        assert L.licencia_activa(emp)["estado"] == "suspendida"
    finally:
        _limpia(db, emp)


# ── P1.1 Login multiempresa ──────────────────────────────────────────────────
def test_login_multiempresa(db):
    e1, e2 = _emp(), _emp()
    uid = 990111
    try:
        ME.vincular(uid, e1, rol="ADMINISTRADOR")
        ME.vincular(uid, e2, rol="GERENTE")
        disp = {x["id_empresa"] for x in ME.empresas_disponibles(uid)}
        assert e1 in disp and e2 in disp
        assert ME.cambiar_empresa_activa(uid, e1) is True
        from src.db.empresa import empresa_actual_id
        assert empresa_actual_id() == e1
        assert ME.cambiar_empresa_activa(uid, _emp()) is False   # empresa ajena
    finally:
        from src.db.empresa import set_empresa_actual
        set_empresa_actual(EMPRESA_DEFAULT_ID)
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM usuarios_empresas WHERE id_usuario=%s", (uid,))
            conn.commit()


# ── P1.2 Restore tenant (export → import) ────────────────────────────────────
def test_restore_tenant(db):
    emp = _emp()
    try:
        L.asignar_plan(emp, "PLUS")                # crea fila empresa_licencia
        exp = BT.exportar_empresa(emp)
        assert exp["ruta"] and os.path.exists(exp["ruta"])
        # borra y restaura
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM empresa_licencia WHERE id_empresa=%s", (emp,))
            conn.commit()
        r = BT.restaurar_empresa(exp["ruta"], id_empresa=emp)
        assert r["ok"] and r["filas"] >= 1
        assert L.licencia_activa(emp) is not None    # recuperada
        os.remove(exp["ruta"])
    finally:
        _limpia(db, emp)


# ── P1.3 Branding real (impacta en documento AEAT) ───────────────────────────
def test_branding_en_documento(db):
    emp = _emp()
    try:
        BR.set_branding(emp, nombre_comercial="MarcaTenant SL")
        from src.services.aeat import documento as DOC
        assert DOC._empresa_nombre(emp) == "MarcaTenant SL"   # el PDF usará este nombre
    finally:
        _limpia(db, emp)


# ── P1.4 Facturas SaaS PDF ───────────────────────────────────────────────────
def test_facturas_pdf(db):
    emp = _emp()
    try:
        S.crear(emp, "PLUS", prueba=False, proveedor="simulado")   # emite factura
        fs = FAC.listar_facturas(emp)
        assert fs
        ruta = FAC.factura_pdf(fs[0]["id"], id_empresa=emp)
        assert ruta and os.path.exists(ruta)
        os.remove(ruta)
    finally:
        _limpia(db, emp)


# ── P2.2 Hardening aislamiento ───────────────────────────────────────────────
def test_aislamiento_tablas_clave(db):
    # Tablas de negocio clave deben estar aisladas por tenant.
    for t in ("ventas", "facturas_cliente", "compras_facturas", "empresa_licencia",
              "suscripciones", "notificaciones", "wf_instancias", "bi_kpi_valores"):
        assert AIS.verificar(t) is True
    assert AIS.verificar("permisos") is True       # global declarada
