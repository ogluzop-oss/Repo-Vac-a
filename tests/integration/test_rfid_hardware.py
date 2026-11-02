"""
Configuración de hardware RFID real (`db.rfid_hardware` + `services.rfid.hardware.
resolver_gateway`): IP/puerto/modo por (empresa, centro), con fallback a empresa-wide y
degradación honesta a modo simulado cuando no hay IP configurada — BD real (`*_test`)."""

import pytest

from src.db import rfid_hardware as rfid_db
from src.services.rfid import hardware as rfid_hw

pytestmark = pytest.mark.db


@pytest.fixture
def emp(fab):
    return fab.empresa("RFID HARDWARE CONFIG TEST")


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rfid_lectores WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_obtener_config_sin_fila_degrada_a_simulado(db, emp):
    cfg = rfid_db.obtener_config(emp, "CENTRO-X")
    assert cfg["modo"] == "simulado"
    assert cfg["ip"] is None
    assert cfg["puerto"] == 5084


def test_guardar_y_obtener_config_por_centro(db, emp):
    r = rfid_db.guardar_config(emp, "CENTRO-A", modo="fisico", ip="10.1.2.3", puerto=5084)
    assert r["ok"] is True
    cfg = rfid_db.obtener_config(emp, "CENTRO-A")
    assert cfg["modo"] == "fisico" and cfg["ip"] == "10.1.2.3" and cfg["puerto"] == 5084


def test_guardar_config_actualiza_fila_existente_mismo_centro(db, emp):
    rfid_db.guardar_config(emp, "CENTRO-A", modo="fisico", ip="10.1.2.3")
    rfid_db.guardar_config(emp, "CENTRO-A", modo="fisico", ip="10.1.2.99")
    cfg = rfid_db.obtener_config(emp, "CENTRO-A")
    assert cfg["ip"] == "10.1.2.99"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM rfid_lectores WHERE id_empresa=%s AND id_centro='CENTRO-A'",
                    (emp,))
        n = cur.fetchone()
        n = n[0] if not isinstance(n, dict) else list(n.values())[0]
        assert n == 1  # upsert, nunca duplica fila


def test_config_empresa_wide_es_fallback_sin_fila_de_centro(db, emp):
    rfid_db.guardar_config(emp, "", modo="fisico", ip="10.9.9.9")
    cfg = rfid_db.obtener_config(emp, "CENTRO-SIN-CONFIG-PROPIA")
    assert cfg["ip"] == "10.9.9.9"


def test_config_de_centro_especifico_tiene_prioridad_sobre_empresa_wide(db, emp):
    rfid_db.guardar_config(emp, "", modo="fisico", ip="10.0.0.1")
    rfid_db.guardar_config(emp, "CENTRO-B", modo="fisico", ip="10.0.0.2")
    assert rfid_db.obtener_config(emp, "CENTRO-B")["ip"] == "10.0.0.2"
    assert rfid_db.obtener_config(emp, "CENTRO-OTRO")["ip"] == "10.0.0.1"


def test_guardar_config_modo_invalido_se_normaliza(db, emp):
    rfid_db.guardar_config(emp, "CENTRO-C", modo="valor-cualquiera", ip="10.0.0.5")
    assert rfid_db.obtener_config(emp, "CENTRO-C")["modo"] == "simulado"


def test_eliminar_config_desactiva_y_cae_a_fallback(db, emp):
    rfid_db.guardar_config(emp, "", modo="fisico", ip="10.0.0.1")
    rfid_db.guardar_config(emp, "CENTRO-D", modo="fisico", ip="10.0.0.2")
    assert rfid_db.eliminar_config(emp, "CENTRO-D") is True
    assert rfid_db.obtener_config(emp, "CENTRO-D")["ip"] == "10.0.0.1"


# ── resolver_gateway ────────────────────────────────────────────────────────
def test_resolver_gateway_sin_config_da_simulado(db, emp):
    gw = rfid_hw.resolver_gateway(emp, "CENTRO-SIN-CONFIG")
    assert gw.modo_simulado is True


def test_resolver_gateway_fisico_con_ip_da_gateway_real(db, emp):
    rfid_db.guardar_config(emp, "CENTRO-E", modo="fisico", ip="10.5.5.5", puerto=5084)
    gw = rfid_hw.resolver_gateway(emp, "CENTRO-E")
    assert gw.modo_simulado is False
    assert gw.ip == "10.5.5.5"
    assert gw.puerto == 5084


def test_resolver_gateway_fisico_sin_ip_degrada_honesto_a_simulado(db, emp):
    """Insert directo (sin pasar por guardar_config, que exige IP en modo físico desde la UI) para
    cubrir el caso defensivo de una fila con modo='fisico' pero ip=NULL en BD."""
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO rfid_lectores (id_empresa, id_centro, modo, ip) "
                    "VALUES (%s,%s,'fisico',NULL)", (emp, "CENTRO-F"))
        conn.commit()
    gw = rfid_hw.resolver_gateway(emp, "CENTRO-F")
    assert gw.modo_simulado is True  # nunca intenta una IP vacía
