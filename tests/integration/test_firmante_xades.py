"""Integración · FirmanteXAdES (C3.5.3): firma XAdES reutilizable desde la custodia."""

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
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DEMO SELLO"),
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
        cur.execute("DELETE FROM fiscal_certificados WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM fiscal_config WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


_XML = '<Factura xmlns="urn:demo" Id="F1"><Importe>10.00</Importe></Factura>'


def test_firma_xades_bes(db, fab, p12):
    from src.services.fiscal import certificados as C
    from src.services.fiscal.firmantes import FirmanteXAdES
    blob, pw = p12
    emp = fab.empresa("XADES BES")
    fab.al_limpiar(lambda: _borra(db, emp))
    C.importar(blob, pw, id_empresa=emp)
    firmante = FirmanteXAdES(C.proveedor_claves(emp))
    assert firmante.disponible()
    firmado = firmante.firmar_xml(_XML, reference_uri="#F1")
    assert firmado and b"QualifyingProperties" in firmado and b"Signature" in firmado


def test_firma_xades_epes_con_politica(db, fab, p12):
    import base64
    import hashlib
    from src.services.fiscal import certificados as C
    from src.services.fiscal.firmantes import FirmanteXAdES, politica_epes
    blob, pw = p12
    emp = fab.empresa("XADES EPES")
    fab.al_limpiar(lambda: _borra(db, emp))
    C.importar(blob, pw, id_empresa=emp)
    pol = politica_epes("urn:demo:policy", "demo",
                        base64.b64encode(hashlib.sha1(b"demo").digest()).decode())
    firmado = FirmanteXAdES(C.proveedor_claves(emp), policy=pol).firmar_xml(_XML, reference_uri="#F1")
    assert firmado and b"SignaturePolicyIdentifier" in firmado


def test_factory_firmante_segun_modo(db, fab, p12):
    from src.db import fiscal as F
    from src.services.fiscal import certificados as C
    from src.services.fiscal.factory import firmante_para
    from src.services.fiscal.firmantes import FirmanteXAdES
    blob, pw = p12
    emp = fab.empresa("XADES MODO")
    fab.al_limpiar(lambda: _borra(db, emp))
    C.importar(blob, pw, id_empresa=emp)
    # VERI*FACTU → no se firma (no-op).
    F.guardar_config(proveedor="verifactu", modo="verifactu", id_empresa=emp)
    assert not isinstance(firmante_para(F.obtener_config(emp)), FirmanteXAdES)
    # NO-VERIFACTU con certificado → FirmanteXAdES.
    F.guardar_config(modo="no_verifactu", id_empresa=emp)
    assert isinstance(firmante_para(F.obtener_config(emp)), FirmanteXAdES)


def test_firmante_sin_certificado_no_disponible(db, fab):
    from src.services.fiscal.firmantes import FirmanteXAdES
    f = FirmanteXAdES(None)
    assert f.disponible() is False and f.firmar_xml(_XML) is None
