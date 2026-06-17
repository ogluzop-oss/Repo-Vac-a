"""Integración · transporte mTLS en memoria + cableado del emisor (C3.5.2)."""

import datetime as dt

import pytest

pytestmark = pytest.mark.db


def _p12(nif="B12345678", dias=365, password="clave-p12"):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (BestAvailableEncryption,
                                                              pkcs12)
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DEMO SELLO"),
                   x509.NameAttribute(NameOID.SERIAL_NUMBER, "IDCES-" + nif)])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(n).issuer_name(n)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=dias)).sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(
        b"demo", key, cert, None, BestAvailableEncryption(password.encode())), password


@pytest.fixture(scope="module")
def p12():
    return _p12()


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM fiscal_certificados WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM fiscal_config WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_contexto_mtls_en_memoria(db, fab, p12):
    from src.services.fiscal import certificados as C
    from src.services.fiscal.emisores.tls import contexto_mtls
    from urllib3.contrib.pyopenssl import PyOpenSSLContext
    blob, pw = p12
    emp = fab.empresa("TLS CTX")
    fab.al_limpiar(lambda: _borra(db, emp))
    C.importar(blob, pw, id_empresa=emp)
    ctx = contexto_mtls(C.proveedor_claves(emp))
    assert isinstance(ctx, PyOpenSSLContext)        # contexto en memoria (sin ficheros)


def test_emisor_con_certificado_esta_disponible(db, fab, p12):
    from src.services.fiscal import certificados as C
    from src.db import fiscal as F
    from src.services.fiscal.factory import emisor_para
    blob, pw = p12
    emp = fab.empresa("TLS EMI")
    fab.al_limpiar(lambda: _borra(db, emp))
    F.guardar_config(proveedor="verifactu", activo=1, id_empresa=emp)
    # Sin certificado → emisor no disponible.
    assert emisor_para(F.obtener_config(emp)).disponible() is False
    # Con certificado activo → emisor disponible (transporte mTLS inyectado).
    C.importar(blob, pw, id_empresa=emp)
    assert emisor_para(F.obtener_config(emp)).disponible() is True


def test_transporte_mtls_es_callable(db, fab, p12):
    from src.services.fiscal import certificados as C
    from src.services.fiscal.emisores.tls import transporte_mtls
    blob, pw = p12
    emp = fab.empresa("TLS TRANS")
    fab.al_limpiar(lambda: _borra(db, emp))
    C.importar(blob, pw, id_empresa=emp)
    t = transporte_mtls(C.proveedor_claves(emp))
    assert callable(t)
    assert transporte_mtls(None) is None


def test_alerta_caducidad(db, fab):
    from src.services.fiscal import certificados as C
    from src.services.fiscal.emisores.tls import revisar_caducidad
    emp = fab.empresa("TLS CAD")
    fab.al_limpiar(lambda: _borra(db, emp))
    # Sin certificado.
    assert revisar_caducidad(emp)["estado"] == "sin_certificado"
    # Certificado que caduca pronto.
    blob, pw = _p12(dias=10)
    C.importar(blob, pw, id_empresa=emp)
    r = revisar_caducidad(emp, dias_aviso=30)
    assert r["estado"] == "por_caducar" and r["aviso"] is True
