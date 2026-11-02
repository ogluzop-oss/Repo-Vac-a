"""
`gui.components.remote_scan._centro_codigo_activo`/`_token_desktop`: el token de escaneo remoto
emitido para la sesión de escritorio debe reflejar la TIENDA ACTIVA del proceso (la que fija
"Cambiar de centro"), no solo `usuarios.centro_codigo` a secas — un SUPERADMIN no tiene centro fijo
propio (NULL en BD) y antes de este fix `crear_solicitud` siempre fallaba con "sin tienda/almacén
asignado" para él, aunque tuviera una tienda activa recién seleccionada."""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def tienda_test(db, fab):
    emp = fab.EMP_DEFECTO
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO tiendas (nombre, activo, id_empresa, codigo_tienda) "
                    "VALUES (%s,1,%s,%s)", ("Tienda Test Remote Scan", emp, "RS-TEST-01"))
        tid = cur.lastrowid
        conn.commit()
    fab.al_limpiar(lambda: _del_tienda(db, tid))
    return tid


def _del_tienda(db, tid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM tiendas WHERE id=%s", (tid,))
        conn.commit()


def test_centro_codigo_activo_resuelve_desde_tienda_activa(db, fab, tienda_test, monkeypatch):
    from src.db import empresa as emp_db
    from src.gui.components import remote_scan

    monkeypatch.setattr(emp_db, "tienda_actual_id", lambda: tienda_test)
    assert remote_scan._centro_codigo_activo() == "RS-TEST-01"


def test_centro_codigo_activo_sin_tienda_activa_da_none(monkeypatch):
    from src.db import empresa as emp_db
    from src.gui.components import remote_scan

    monkeypatch.setattr(emp_db, "tienda_actual_id", lambda: None)
    assert remote_scan._centro_codigo_activo() is None


def test_token_desktop_superadmin_sin_centro_fijo_usa_tienda_activa(db, fab, tienda_test, monkeypatch):
    """Caso real del bug: `usuarios.centro_codigo` es None (superadmin flotante) pero hay una
    tienda activa seleccionada — el token debe llevar el `centro_codigo` de ESA tienda, no None."""
    from src.db import empresa as emp_db
    from src.db.usuario import sesion_global
    from src.gui.components import remote_scan
    from src.seguridad import tokens

    monkeypatch.setattr(emp_db, "tienda_actual_id", lambda: tienda_test)
    monkeypatch.setattr(sesion_global, "usuario_actual",
                        {"id": 999, "id_empresa": fab.EMP_DEFECTO, "perfil": "SUPERADMIN",
                         "nombre": "SUPER TEST", "centro_codigo": None})

    tok = remote_scan._token_desktop()
    assert tok is not None
    claims = tokens.decodificar(tok) if hasattr(tokens, "decodificar") else None
    if claims is None:
        import jwt
        claims = jwt.decode(tok, options={"verify_signature": False})
    assert claims["tienda"] == "RS-TEST-01"


def test_token_desktop_empleado_normal_sin_tienda_activa_usa_su_centro_fijo(monkeypatch):
    """Caso normal (sin cambios de comportamiento): un empleado con centro propio, sin override
    ambiente, sigue usando su `centro_codigo` de siempre."""
    from src.db import empresa as emp_db
    from src.db.usuario import sesion_global
    from src.gui.components import remote_scan
    from src.seguridad import tokens

    monkeypatch.setattr(emp_db, "tienda_actual_id", lambda: None)
    monkeypatch.setattr(sesion_global, "usuario_actual",
                        {"id": 1, "id_empresa": "EMP-1", "perfil": "OPERARIO",
                         "nombre": "EMPLEADO TEST", "centro_codigo": "EMP-CENTRO-FIJO"})

    tok = remote_scan._token_desktop()
    assert tok is not None
    import jwt
    claims = jwt.decode(tok, options={"verify_signature": False})
    assert claims["tienda"] == "EMP-CENTRO-FIJO"
