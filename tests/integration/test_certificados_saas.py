"""Integración · SaaS/multiempresa de certificados (C3.5.4): fronteras + auditoría."""

import datetime as dt

import pytest

pytestmark = pytest.mark.db


def _p12(nif="B12345678", password="clave-p12"):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (BestAvailableEncryption,
                                                              pkcs12)
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DEMO"),
                   x509.NameAttribute(NameOID.SERIAL_NUMBER, "IDCES-" + nif)])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(n).issuer_name(n)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=365)).sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(
        b"demo", key, cert, None, BestAvailableEncryption(password.encode())), password


@pytest.fixture(scope="module")
def p12():
    return _p12()


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM fiscal_certificados_auditoria WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM fiscal_certificados WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_frontera_tenant_no_ve_certificados_de_otro(db, fab, p12):
    from src.services.fiscal import certificados as C
    blob, pw = p12
    a = fab.empresa("SAAS A"); b = fab.empresa("SAAS B")
    fab.al_limpiar(lambda: (_borra(db, a), _borra(db, b)))
    ma = C.importar(blob, pw, id_empresa=a)
    # B no ve el certificado de A ni puede activarlo/revocarlo (filtro por id_empresa).
    assert C.listar(b) == []
    assert C.activar(ma["id"], b) is False
    assert C.revocar(ma["id"], b) is False
    # A sigue intacto y activo.
    assert C.obtener_activo(a)["id"] == ma["id"]


def test_auditoria_registra_y_esta_aislada(db, fab, p12):
    from src.services.fiscal import certificados as C
    blob, pw = p12
    a = fab.empresa("SAAS AUD A"); b = fab.empresa("SAAS AUD B")
    fab.al_limpiar(lambda: (_borra(db, a), _borra(db, b)))
    m1 = C.importar(blob, pw, id_empresa=a)
    C.importar(blob, pw, id_empresa=a)            # sustitución
    C.revocar(m1["id"], a)
    C.rotar_cifrado(a)
    C.importar(blob, pw, id_empresa=b)            # evento de B

    acciones_a = [e["accion"] for e in C.listar_auditoria(a)]
    assert "importar" in acciones_a and "revocar" in acciones_a and "rotar" in acciones_a
    # La auditoría de A no incluye eventos de B y viceversa.
    aud_b = C.listar_auditoria(b)
    assert all(e["id_empresa"] == b for e in aud_b)
    assert len(aud_b) == 1 and aud_b[0]["accion"] == "importar"
