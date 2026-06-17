"""Integración · firma XAdES-EPES de Facturae (C3.4.3) reutilizando C3.5."""

import datetime as dt

import pytest

pytestmark = pytest.mark.db

_EMISOR = {"nif": "A12345674", "razon_social": "EMISOR SL", "persona": "J", "residencia": "R",
           "direccion": "Calle 1", "cp": "28001", "municipio": "Madrid",
           "provincia": "Madrid", "cod_pais": "ESP"}
_RECEPTOR = {"nif": "B12345678", "razon_social": "CLIENTE SL", "persona": "J", "residencia": "R",
             "direccion": "Calle 2", "cp": "08001", "municipio": "Barcelona",
             "provincia": "Barcelona", "cod_pais": "ESP"}


def _p12(password="clave-p12"):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (BestAvailableEncryption, pkcs12)
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EMISOR SL"),
                   x509.NameAttribute(NameOID.SERIAL_NUMBER, "IDCES-A12345674")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=365)).sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(b"d", key, cert, None,
                                                 BestAvailableEncryption(password.encode())), password


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM fiscal_certificados WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _facturae():
    from src.services.fiscal.facturae import facturae_xml as FX
    datos = FX.normalizar(_EMISOR, _RECEPTOR,
                          [{"descripcion": "X", "cantidad": 1, "subtotal": 12.10, "iva": 21.0}],
                          numero="FAC/1", fecha="2026-06-16")
    return FX.facturae_xml(datos)


def test_firma_facturae_xades_epes(db, fab):
    from src.services.fiscal import certificados as C
    from src.services.fiscal.facturae import firma
    blob, pw = _p12()
    emp = fab.empresa("FE FIRMA")
    fab.al_limpiar(lambda: _borra(db, emp))
    C.importar(blob, pw, id_empresa=emp)
    firmado = firma.firmar_facturae(_facturae(), C.proveedor_claves(emp))
    assert firmado
    assert b"Signature" in firmado and b"QualifyingProperties" in firmado
    assert b"SignaturePolicyIdentifier" in firmado          # XAdES-EPES
    assert firma.POLITICA_ID.encode() in firmado


def test_facturae_firmado_sigue_validando_xsd(db, fab):
    from src.services.fiscal import certificados as C
    from src.services.fiscal.facturae import esquemas as E, firma
    blob, pw = _p12()
    emp = fab.empresa("FE FIRMA XSD")
    fab.al_limpiar(lambda: _borra(db, emp))
    C.importar(blob, pw, id_empresa=emp)
    firmado = firma.firmar_facturae(_facturae(), C.proveedor_claves(emp))
    ok, err = E.validar(firmado, "3.2.2")
    assert ok, err                                          # ds:Signature permitido por el XSD


def test_firma_sin_certificado(db, fab):
    from src.services.fiscal.facturae import firma
    emp = fab.empresa("FE SIN CERT")
    fab.al_limpiar(lambda: _borra(db, emp))
    from src.services.fiscal import certificados as C
    assert firma.firmar_facturae(_facturae(), C.proveedor_claves(emp)) is None
