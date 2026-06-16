"""Integración · login por identidad (usuario único por empresa) + sesiones/refresh."""

import pytest

pytestmark = pytest.mark.db


def test_login_por_identidad_y_aislamiento_empresa(db, fab):
    from src.db import usuario as U
    emp_b = fab.empresa("EMP B IDENT")
    # Mismo nombre en dos empresas (permitido por el unique compuesto C1.4).
    ua = fab.usuario(nombre="MISMO_NOMBRE", password="Clave_A_123456", id_empresa=fab.EMP_DEFECTO)
    ub = fab.usuario(nombre="MISMO_NOMBRE", password="Clave_B_123456", id_empresa=emp_b)
    # Con id_empresa se resuelve la identidad correcta.
    ra = U.validar_login_usuario("MISMO_NOMBRE", "Clave_A_123456", id_empresa=fab.EMP_DEFECTO)
    rb = U.validar_login_usuario("MISMO_NOMBRE", "Clave_B_123456", id_empresa=emp_b)
    assert ra and ra["id"] == ua["id"]
    assert rb and rb["id"] == ub["id"]
    # La contraseña de A no vale para la identidad de B.
    assert U.validar_login_usuario("MISMO_NOMBRE", "Clave_A_123456", id_empresa=emp_b) is None


def test_login_por_email(db, fab):
    from src.db import usuario as U
    u = fab.usuario(nombre="USR_EMAIL", password="Clave_Email_123", email="ana@empresa.com")
    res = U.validar_login_usuario("ana@empresa.com", "Clave_Email_123")
    assert res and res["id"] == u["id"]


def test_sesiones_refresh_registrar_validar_revocar(db, fab):
    from src.db import sesiones
    from src.seguridad import tokens
    u = fab.usuario(nombre="USR_SES", password="Clave_Ses_123456")
    usuario = {"id": u["id"], "id_empresa": fab.EMP_DEFECTO, "tienda_id": None, "perfil": "OPERARIO"}
    tok, jti, expira = tokens.emitir_refresh(usuario)
    fab.al_limpiar(lambda: _borra_sesion(db, jti))
    assert sesiones.registrar(u["id"], jti, tokens.hash_refresh(tok), expira)
    assert sesiones.es_valido(jti, tokens.hash_refresh(tok)) is True
    assert sesiones.es_valido(jti, "hash-que-no-coincide") is False
    assert sesiones.revocar(jti)
    assert sesiones.es_valido(jti, tokens.hash_refresh(tok)) is False


def _borra_sesion(db, jti):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM sesiones WHERE jti=%s", (jti,))
        conn.commit()
