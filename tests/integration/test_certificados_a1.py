"""A1 (seguridad) · el material PKCS#12 NUNCA se almacena sin cifrado efectivo."""

import datetime as dt

import pytest

pytestmark = pytest.mark.db


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


def _cuenta(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM fiscal_certificados WHERE id_empresa=%s", (emp,))
        return cur.fetchone()[0]


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM fiscal_certificados WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_cripto_tenant_fail_closed(monkeypatch):
    """Sin backend de cifrado, cifrar() devuelve None (nunca un sustituto en claro)."""
    from src.services.fiscal import cripto_tenant
    monkeypatch.setattr("src.utils.cripto.claves_raiz", lambda: [])           # sin claves derivables
    monkeypatch.setattr("src.utils.cripto.cifrado_disponible", lambda: False)  # sin backend
    assert cripto_tenant.cifrar(b"secreto", "emp-x") is None
    assert cripto_tenant.disponible() is False


def test_importar_falla_sin_cifrado_y_no_almacena(db, fab, monkeypatch):
    from src.services.fiscal import certificados as C
    blob, pw = _p12()
    emp = fab.empresa("A1 NO CIFRADO")
    fab.al_limpiar(lambda: _borra(db, emp))
    monkeypatch.setattr("src.services.fiscal.cripto_tenant.disponible", lambda: False)
    assert C.importar(blob, pw, id_empresa=emp) is None       # fail-fast
    assert _cuenta(db, emp) == 0                              # NADA almacenado


def test_importar_falla_si_cifrado_no_produce_token(db, fab, monkeypatch):
    """Defensa en profundidad: si cifrar() devolviera algo no cifrado, se aborta."""
    from src.services.fiscal import certificados as C
    blob, pw = _p12()
    emp = fab.empresa("A1 DEFENSA")
    fab.al_limpiar(lambda: _borra(db, emp))
    monkeypatch.setattr("src.services.fiscal.cripto_tenant.disponible", lambda: True)
    monkeypatch.setattr("src.services.fiscal.cripto_tenant.cifrar",
                        lambda datos, emp: "plain:" + "AAAA")   # simula material no cifrado
    assert C.importar(blob, pw, id_empresa=emp) is None
    assert _cuenta(db, emp) == 0


def test_flujo_normal_cifrado_intacto(db, fab):
    """Con cifrado correctamente configurado, la importación funciona y el material
    queda CIFRADO (token Fernet)."""
    from src.services.fiscal import certificados as C
    blob, pw = _p12()
    emp = fab.empresa("A1 OK")
    fab.al_limpiar(lambda: _borra(db, emp))
    meta = C.importar(blob, pw, id_empresa=emp)
    assert meta and _cuenta(db, emp) == 1
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT material_cifrado FROM fiscal_certificados WHERE id=%s", (meta["id"],))
        material = cur.fetchone()[0]
    assert material.startswith("gAAAA") and "plain:" not in material
    assert C.proveedor_claves(emp).disponible()               # sigue descifrando/usando
