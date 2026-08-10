"""
Tests Etapa F · Fase F6: seguridad operacional.

Verifica la fachada `seguridad.operacion` que COMPONE lo existente: detección de anomalías cableada a
ALERTAS técnicas, rotación de secretos OPERACIONAL verificada (preserva el texto plano), estado de
seguridad (incidentes/secretos/bloqueos/caducidad de tokens) y registro de job. Sin duplicar seguridad.
"""

import pytest

from src.services.seguridad import operacion

pytestmark = pytest.mark.db

EMP = "T-F6"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM auditoria_logs WHERE usuario='atacante_f6'")
            cur.execute("DELETE FROM cd_conexiones WHERE id_empresa=%s", (EMP,))
            conn.commit()
    _b()
    yield
    _b()


def test_escanear_anomalias_abre_incidente_y_alerta(limpia, db):
    # Siembra 5 LOGIN_FALLIDO del mismo usuario/IP en la ventana → fuerza bruta.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for _ in range(5):
            cur.execute("INSERT INTO auditoria_logs (usuario, accion, ip_origen, fecha, id_empresa) "
                        "VALUES ('atacante_f6','LOGIN_FALLIDO','9.9.9.9',NOW(),%s)", (EMP,))
        conn.commit()
    r = operacion.escanear_anomalias(id_empresa=EMP, umbral=5, ventana_min=15, alertar=True)
    assert r["incidentes"] and r["alertas"] >= 1          # detección → incidente → alerta cableada


def test_rotar_secretos_verificado_preserva_plano(limpia):
    from src.services.comercio_digital import conexiones
    conexiones.registrar("sap", nombre="f6", id_empresa=EMP, tipo_auth="oauth2",
                         endpoint_base="https://x", credenciales={"token": "abc-123"})
    assert operacion.secretos_rotables(EMP) >= 1
    # Report-only por defecto: no rota.
    rep = operacion.rotar_secretos(EMP, aplicar=False)
    assert rep["candidatos"] >= 1 and rep["rotados"] == 0
    # Aplicar: rota y VERIFICA que el texto plano se preserva.
    apl = operacion.rotar_secretos(EMP, aplicar=True)
    assert apl["rotados"] >= 1 and apl["omitidos"] == 0
    cred = conexiones.credenciales("sap", nombre="f6", id_empresa=EMP)
    assert cred.get("token") == "abc-123"                 # la credencial sigue siendo usable


def test_estado_seguridad(limpia, db):
    e = operacion.estado_seguridad(EMP)
    assert e["id_empresa"] == EMP
    for k in ("incidentes_abiertos", "secretos_rotables", "cuentas_bloqueadas", "tokens"):
        assert k in e
    assert e["tokens"]["revocable"] is True               # caducidad/revocación ya existentes


def test_registrar_job(db):
    assert operacion.registrar_jobs() is True


def test_descriptor(db):
    d = operacion.descriptor()
    assert d["motor_nuevo"] is False and d["rotacion_verificada"] is True
    assert "secret_manager (rotar)" in d["reutiliza"]
    assert {"escanear_anomalias", "rotar_secretos", "estado_seguridad"} <= set(d["operaciones"])
