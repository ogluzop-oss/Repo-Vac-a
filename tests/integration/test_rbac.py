"""
RBAC / ACL empresarial — roles, permisos, grupos, ACL, legacy, cache, decoradores,
auditoría de seguridad y multiempresa.
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import rbac as R
from src.db.empresa import EMPRESA_DEFAULT_ID
from src.services import autorizacion as A
from src.services.seguridad import catalogo as C

E = EMPRESA_DEFAULT_ID


@pytest.fixture(autouse=True)
def _catalogo():
    C.sincronizar_catalogo()
    A.limpiar_cache()
    yield
    A.limpiar_cache()


def _usuario(db, perfil="OPERARIO"):
    nombre = "RBAC_" + uuid.uuid4().hex[:8]
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO usuarios (nombre, password, perfil, activo) VALUES (%s,'x',%s,1)",
                    (nombre, perfil))
        uid = cur.lastrowid; conn.commit()
    return uid


def _limpia_usuario(db, uid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("usuarios_roles", "usuarios_grupos"):
            cur.execute(f"DELETE FROM {t} WHERE id_usuario=%s", (uid,))
        cur.execute("DELETE FROM usuarios WHERE id=%s", (uid,))
        conn.commit()


# ── Legacy: sin asignaciones RBAC, manda el perfil ───────────────────────────
def test_legacy_fallback(db):
    uid = _usuario(db, "OPERARIO")
    try:
        u = {"id": uid, "perfil": "OPERARIO", "id_empresa": E}
        assert A.puede(u, "ventas.crear") is True
        assert A.puede(u, "contabilidad.cierre") is False
        assert A.puede({"id": uid, "perfil": "ADMINISTRADOR", "id_empresa": E}, "contabilidad.cierre")
        assert A.puede({"id": uid, "perfil": "SUPERADMIN", "id_empresa": E}, "lo.que.sea")  # comodín
    finally:
        _limpia_usuario(db, uid)


# ── RBAC explícito: rol + permiso concreto ───────────────────────────────────
def test_rol_concede_permiso(db):
    uid = _usuario(db, "OPERARIO")
    rid = R.crear_rol("CONTABLE_" + uuid.uuid4().hex[:4], "Contable", id_empresa=E)
    try:
        u = {"id": uid, "perfil": "OPERARIO", "id_empresa": E}
        R.asignar_rol_usuario(uid, rid, id_empresa=E)
        # tiene rol pero sin permisos → deniega (ya NO usa fallback legacy)
        assert A.puede(u, "contabilidad.cierre") is False
        R.asignar_permiso_rol(rid, "contabilidad.cierre", id_empresa=E)
        assert A.puede(u, "contabilidad.cierre") is True       # concedido por rol
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM roles_permisos WHERE id_rol=%s", (rid,))
            cur.execute("DELETE FROM usuarios_roles WHERE id_rol=%s", (rid,))
            cur.execute("DELETE FROM roles WHERE id=%s", (rid,))
            conn.commit()
        _limpia_usuario(db, uid)


# ── Grupos ────────────────────────────────────────────────────────────────────
def test_grupo_concede_permiso(db):
    uid = _usuario(db, "OPERARIO")
    gid = R.crear_grupo("GRP_" + uuid.uuid4().hex[:4], "Grupo Tes", id_empresa=E)
    try:
        u = {"id": uid, "perfil": "OPERARIO", "id_empresa": E}
        R.asignar_grupo_usuario(uid, gid, id_empresa=E)
        R.asignar_permiso_grupo(gid, "tesoreria.remesas.generar", id_empresa=E)
        assert A.puede(u, "tesoreria.remesas.generar") is True
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM grupos_permisos WHERE id_grupo=%s", (gid,))
            cur.execute("DELETE FROM usuarios_grupos WHERE id_grupo=%s", (gid,))
            cur.execute("DELETE FROM grupos WHERE id=%s", (gid,))
            conn.commit()
        _limpia_usuario(db, uid)


# ── ACL: denegación explícita sobre un recurso gana ──────────────────────────
def test_acl_deny_override(db):
    uid = _usuario(db, "OPERARIO")
    rid = R.crear_rol("DOCS_" + uuid.uuid4().hex[:4], "Docs", id_empresa=E)
    try:
        u = {"id": uid, "perfil": "OPERARIO", "id_empresa": E}
        R.asignar_rol_usuario(uid, rid, id_empresa=E)
        R.asignar_permiso_rol(rid, "documentos.eliminar", id_empresa=E)
        assert A.puede(u, "documentos.eliminar", recurso_tipo="factura", recurso_id="F1") is True
        # ACL deny sobre la factura F1 para este usuario
        R.set_acl("factura", "F1", "usuario", uid, "eliminar", permitido=False, id_empresa=E)
        assert A.puede(u, "documentos.eliminar", recurso_tipo="factura", recurso_id="F1") is False
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM acl_recursos WHERE id_empresa=%s AND sujeto_id=%s", (E, str(uid)))
            cur.execute("DELETE FROM roles_permisos WHERE id_rol=%s", (rid,))
            cur.execute("DELETE FROM usuarios_roles WHERE id_rol=%s", (rid,))
            cur.execute("DELETE FROM roles WHERE id=%s", (rid,))
            conn.commit()
        _limpia_usuario(db, uid)


# ── Caché: se invalida al cambiar permisos ───────────────────────────────────
def test_cache_invalidacion(db):
    uid = _usuario(db, "OPERARIO")
    rid = R.crear_rol("CACHE_" + uuid.uuid4().hex[:4], "Cache", id_empresa=E)
    try:
        u = {"id": uid, "perfil": "OPERARIO", "id_empresa": E}
        R.asignar_rol_usuario(uid, rid, id_empresa=E)
        assert A.puede(u, "aeat.presentar") is False       # cachea (sin permiso)
        R.asignar_permiso_rol(rid, "aeat.presentar", id_empresa=E)   # invalida caché
        assert A.puede(u, "aeat.presentar") is True
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM roles_permisos WHERE id_rol=%s", (rid,))
            cur.execute("DELETE FROM usuarios_roles WHERE id_rol=%s", (rid,))
            cur.execute("DELETE FROM roles WHERE id=%s", (rid,))
            conn.commit()
        _limpia_usuario(db, uid)


# ── Decorador + denegación auditada ──────────────────────────────────────────
def test_decorador_y_auditoria(db):
    uid = _usuario(db, "OPERARIO")
    try:
        @A.requiere_permiso("contabilidad.cierre")
        def operacion_critica(actor=None):
            return "ok"
        # OPERARIO legacy NO puede → ErrorAutorizacion + traza PERMISO_DENEGADO
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM auditoria_logs WHERE accion='PERMISO_DENEGADO'")
            antes = cur.fetchone()[0]
        with pytest.raises(A.ErrorAutorizacion):
            operacion_critica(actor={"id": uid, "perfil": "OPERARIO", "id_empresa": E})
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM auditoria_logs WHERE accion='PERMISO_DENEGADO'")
            assert cur.fetchone()[0] > antes
        # ADMIN sí
        assert operacion_critica(actor={"id": uid, "perfil": "ADMINISTRADOR", "id_empresa": E}) == "ok"
    finally:
        _limpia_usuario(db, uid)


# ── Multiempresa: roles del sistema por empresa, aislados ────────────────────
def test_multiempresa_roles_sistema(db, fab):
    emp2 = fab.empresa("RBAC B")
    res = C.sincronizar_roles_sistema(emp2)
    assert res["roles"] >= 4
    roles_b = {r["codigo"] for r in R.listar_roles(emp2)}
    assert {"OPERARIO", "GERENTE", "ADMINISTRADOR", "SUPERADMIN"} <= roles_b
    # los roles de emp2 no aparecen en la empresa por defecto salvo que existan allí también
    assert all(r["id_empresa"] == emp2 for r in R.listar_roles(emp2))


# ── Operación crítica protegida (AEAT) bajo sesión sin permiso ───────────────
def test_guard_aeat_presentar(db, fab):
    from src.services.aeat import base as B, estados as ST
    from src.services.contabilidad import cuentas as K
    from src.db.usuario import sesion_global
    from src.db.empresa import contexto_tenant
    K.activar(E)
    uid = _usuario(db, "OPERARIO")
    with contexto_tenant(E, None):
        did = B.guardar_declaracion("303", 2040, "1T", 0.0, [{"casilla": "01", "descripcion": "x", "importe": 0}],
                                    id_empresa=E)
    try:
        # Simula sesión OPERARIO activa → presentar debe ser denegado
        sesion_global.usuario_actual = {"id": uid, "perfil": "OPERARIO", "id_empresa": E}
        with pytest.raises(A.ErrorAutorizacion):
            B.cambiar_estado(did, ST.PRESENTADO, id_empresa=E)
        # ADMIN sí puede
        sesion_global.usuario_actual = {"id": uid, "perfil": "ADMINISTRADOR", "id_empresa": E}
        assert B.cambiar_estado(did, ST.PRESENTADO, id_empresa=E)
    finally:
        sesion_global.usuario_actual = {}
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE l FROM aeat_declaracion_lineas l JOIN aeat_declaraciones d "
                        "ON d.id=l.id_declaracion WHERE d.id_empresa=%s AND d.ejercicio=2040", (E,))
            cur.execute("DELETE FROM aeat_declaraciones WHERE id_empresa=%s AND ejercicio=2040", (E,))
            conn.commit()
        _limpia_usuario(db, uid)
