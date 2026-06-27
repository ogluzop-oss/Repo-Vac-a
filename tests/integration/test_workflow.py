"""
Workflow / BPM — motor, multinivel por importe, rechazo, varios aprobadores, delegación,
SLA/escalado, auditoría, bandeja, multiempresa y no-intrusividad (sin definición → no bloquea).
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import workflow as W
from src.db.empresa import EMPRESA_DEFAULT_ID
from src.services.workflow import plantillas as P, workflow_engine as E

EMP = EMPRESA_DEFAULT_ID
ADM = {"id": 8001, "perfil": "ADMINISTRADOR", "id_empresa": EMP}
OPE = {"id": 8002, "perfil": "OPERARIO", "id_empresa": EMP}


@pytest.fixture(autouse=True)
def _plantillas():
    P.seed_plantillas(EMP)
    yield


def _limpia(db, entidad, eid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM wf_instancias WHERE entidad=%s AND entidad_id=%s", (entidad, str(eid)))
        for r in cur.fetchall():
            iid = r[0] if not isinstance(r, dict) else list(r.values())[0]
            cur.execute("DELETE FROM wf_tareas WHERE id_instancia=%s", (iid,))
            cur.execute("DELETE FROM wf_log WHERE id_instancia=%s", (iid,))
            cur.execute("DELETE FROM wf_instancias WHERE id=%s", (iid,))
        conn.commit()


# ── No intrusivo: entidad sin definición → no bloquea ────────────────────────
def test_sin_definicion_no_bloquea(db):
    r = E.iniciar_proceso("entidad_inexistente_xyz", "X1", contexto={}, actor=ADM, id_empresa=EMP)
    assert r["workflow"] is False
    assert E.aprobado("entidad_inexistente_xyz", "X1", EMP) is True


# ── Importe bajo umbral → auto-aprobado ──────────────────────────────────────
def test_importe_bajo_umbral_autoaprueba(db):
    eid = "PB_" + uuid.uuid4().hex[:6]
    try:
        r = E.iniciar_proceso("compras_pedido", eid, contexto={"importe": 200}, actor=ADM, id_empresa=EMP)
        assert r["workflow"] and r["estado"] == "APROBADO" and r["tarea"] is None
    finally:
        _limpia(db, "compras_pedido", eid)


# ── Multinivel por importe ───────────────────────────────────────────────────
def test_multinivel_por_importe(db):
    eid = "PM_" + uuid.uuid4().hex[:6]
    try:
        r = E.iniciar_proceso("compras_pedido", eid, contexto={"importe": 25000}, actor=ADM, id_empresa=EMP)
        assert r["estado"] == "EN_CURSO"
        a = E.aprobar_tarea(r["tarea"], actor=ADM, id_empresa=EMP); assert a["estado"] == "EN_CURSO"
        a = E.aprobar_tarea(a["tarea"], actor=ADM, id_empresa=EMP); assert a["estado"] == "EN_CURSO"
        a = E.aprobar_tarea(a["tarea"], actor=ADM, id_empresa=EMP); assert a["estado"] == "APROBADO"  # 3 niveles
    finally:
        _limpia(db, "compras_pedido", eid)


# ── Rechazo ───────────────────────────────────────────────────────────────────
def test_rechazo(db):
    eid = "PR_" + uuid.uuid4().hex[:6]
    try:
        r = E.iniciar_proceso("compras_pedido", eid, contexto={"importe": 6000}, actor=ADM, id_empresa=EMP)
        rr = E.rechazar_tarea(r["tarea"], actor=ADM, comentario="no procede", id_empresa=EMP)
        assert rr["estado"] == "RECHAZADO" and E.aprobado("compras_pedido", eid, EMP) is False
    finally:
        _limpia(db, "compras_pedido", eid)


# ── Autorización: OPERARIO no puede aprobar paso con permiso compras.aprobar ──
def test_operario_no_autorizado(db):
    eid = "PO_" + uuid.uuid4().hex[:6]
    try:
        r = E.iniciar_proceso("compras_pedido", eid, contexto={"importe": 6000}, actor=ADM, id_empresa=EMP)
        with pytest.raises(PermissionError):
            E.aprobar_tarea(r["tarea"], actor=OPE, id_empresa=EMP)
    finally:
        _limpia(db, "compras_pedido", eid)


# ── Varios aprobadores por paso (usuarios_minimos) ───────────────────────────
def test_usuarios_minimos(db):
    did = W.crear_definicion("WF_DOBLE_" + uuid.uuid4().hex[:4], "Doble", "entidad_doble", id_empresa=EMP)
    W.anadir_paso(did, 10, "Doble visto bueno", permiso_requerido="compras.aprobar", usuarios_minimos=2)
    eid = "DOB_" + uuid.uuid4().hex[:6]
    try:
        r = E.iniciar_proceso("entidad_doble", eid, contexto={}, actor=ADM, id_empresa=EMP)
        a = E.aprobar_tarea(r["tarea"], actor=ADM, id_empresa=EMP)
        assert a["estado"] == "EN_CURSO"          # falta el 2º aprobador
        a = E.aprobar_tarea(a["tarea"], actor=ADM, id_empresa=EMP)
        assert a["estado"] == "APROBADO"
    finally:
        _limpia(db, "entidad_doble", eid)
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM wf_pasos WHERE id_definicion=%s", (did,))
            cur.execute("DELETE FROM wf_definiciones WHERE id=%s", (did,))
            conn.commit()


# ── Delegación: el delegado puede aprobar la tarea del usuario asignado ───────
def test_delegacion(db):
    did = W.crear_definicion("WF_DEL_" + uuid.uuid4().hex[:4], "Deleg", "entidad_del", id_empresa=EMP)
    W.anadir_paso(did, 10, "VB usuario", usuarios_minimos=1)   # sin permiso/rol → asignado_usuario
    # asignamos la tarea a un usuario concreto manualmente
    eid = "DEL_" + uuid.uuid4().hex[:6]
    try:
        r = E.iniciar_proceso("entidad_del", eid, contexto={}, actor=ADM, id_empresa=EMP)
        # forzamos asignado_usuario=5000 en la tarea creada
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE wf_tareas SET asignado_usuario=5000 WHERE id=%s", (r["tarea"],))
            conn.commit()
        delegado = {"id": 5001, "perfil": "OPERARIO", "id_empresa": EMP}
        # sin delegación → no autorizado
        with pytest.raises(PermissionError):
            E.aprobar_tarea(r["tarea"], actor=delegado, id_empresa=EMP)
        W.crear_delegacion(5000, 5001, id_empresa=EMP)          # 5000 delega en 5001
        a = E.aprobar_tarea(r["tarea"], actor=delegado, id_empresa=EMP)
        assert a["estado"] == "APROBADO"
    finally:
        _limpia(db, "entidad_del", eid)
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM wf_delegaciones WHERE usuario_origen=5000")
            cur.execute("DELETE FROM wf_pasos WHERE id_definicion=%s", (did,))
            cur.execute("DELETE FROM wf_definiciones WHERE id=%s", (did,))
            conn.commit()


# ── Auditoría: eventos WF_* en auditoria_logs ────────────────────────────────
def test_auditoria_eventos(db):
    eid = "PA_" + uuid.uuid4().hex[:6]
    try:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM auditoria_logs WHERE accion='WF_INICIADO'")
            antes = cur.fetchone()[0]
        E.iniciar_proceso("compras_pedido", eid, contexto={"importe": 6000}, actor=ADM, id_empresa=EMP)
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM auditoria_logs WHERE accion='WF_INICIADO'")
            assert cur.fetchone()[0] > antes
    finally:
        _limpia(db, "compras_pedido", eid)


# ── Bandeja ───────────────────────────────────────────────────────────────────
def test_bandeja(db):
    eid = "PBN_" + uuid.uuid4().hex[:6]
    try:
        E.iniciar_proceso("compras_pedido", eid, contexto={"importe": 6000}, actor=ADM, id_empresa=EMP)
        tareas_adm = E.tareas_para_usuario(ADM, id_empresa=EMP)
        assert any(t.get("entidad") == "compras_pedido" for t in tareas_adm)
        # OPERARIO no ve esa tarea (requiere compras.aprobar)
        tareas_ope = E.tareas_para_usuario(OPE, id_empresa=EMP)
        assert all(t.get("entidad_id") != eid for t in tareas_ope)
    finally:
        _limpia(db, "compras_pedido", eid)


# ── Multiempresa: definiciones independientes ────────────────────────────────
def test_multiempresa(db, fab):
    emp2 = fab.empresa("WF B")
    P.seed_plantillas(emp2)
    # iniciar en emp2 no crea instancia en EMP
    eid = "PMX_" + uuid.uuid4().hex[:6]
    try:
        r = E.iniciar_proceso("compras_pedido", eid, contexto={"importe": 6000},
                              actor={"id": 1, "perfil": "ADMINISTRADOR", "id_empresa": emp2}, id_empresa=emp2)
        assert r["estado"] == "EN_CURSO"
        assert E.estado_entidad("compras_pedido", eid, EMP) is None       # no existe en EMP
        assert E.estado_entidad("compras_pedido", eid, emp2) == "EN_CURSO"
    finally:
        _limpia(db, "compras_pedido", eid)
