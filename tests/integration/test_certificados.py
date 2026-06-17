"""Integración · custodia de certificados fiscales (C3.5.1): cifrado por tenant, historial."""

import datetime as dt

import pytest

pytestmark = pytest.mark.db


def _p12(nif="B12345678", dias=365, password="clave-p12"):
    """Genera un PKCS#12 autofirmado (sello) en memoria para pruebas."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (BestAvailableEncryption,
                                                              pkcs12)
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DEMO SELLO SL"),
                      x509.NameAttribute(NameOID.SERIAL_NUMBER, "IDCES-" + nif)])
    ahora = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(ahora - dt.timedelta(days=1))
            .not_valid_after(ahora + dt.timedelta(days=dias))
            .sign(key, hashes.SHA256()))
    blob = pkcs12.serialize_key_and_certificates(
        b"demo", key, cert, None, BestAvailableEncryption(password.encode()))
    return blob, password


@pytest.fixture(scope="module")
def p12_valido():
    return _p12()


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM fiscal_certificados WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_importar_extrae_metadatos_y_cifra(db, fab, p12_valido):
    from src.services.fiscal import certificados as C
    blob, pw = p12_valido
    emp = fab.empresa("CERT META")
    fab.al_limpiar(lambda: _borra(db, emp))
    meta = C.importar(blob, pw, id_empresa=emp, alias="sello-2026")
    assert meta and meta["estado"] == "activo"
    assert meta["titular_nif"] == "B12345678" and len(meta["huella_cert"]) == 64
    # El material en BD está CIFRADO (no contiene el p12 en claro).
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT material_cifrado FROM fiscal_certificados WHERE id=%s", (meta["id"],))
        material = cur.fetchone()[0]
    assert material.startswith("gAAAA")            # token Fernet, no claro


def test_proveedor_claves_descifra_y_firma(db, fab, p12_valido):
    from src.services.fiscal import certificados as C
    blob, pw = p12_valido
    emp = fab.empresa("CERT CLAVES")
    fab.al_limpiar(lambda: _borra(db, emp))
    C.importar(blob, pw, id_empresa=emp)
    prov = C.proveedor_claves(emp)
    assert prov is not None and prov.disponible()
    assert prov.certificado() is not None and prov.clave_privada() is not None
    firma = prov.firmar(b"hola")
    assert firma and len(firma) > 0


def test_aislamiento_por_tenant(db, fab, p12_valido):
    """El material de una empresa NO se descifra con la clave derivada de otra."""
    from src.services.fiscal import certificados as C, cripto_tenant
    blob, pw = p12_valido
    empA = fab.empresa("CERT A"); empB = fab.empresa("CERT B")
    fab.al_limpiar(lambda: (_borra(db, empA), _borra(db, empB)))
    C.importar(blob, pw, id_empresa=empA)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT material_cifrado FROM fiscal_certificados WHERE id_empresa=%s", (empA,))
        material = cur.fetchone()[0]
    # Con el tenant correcto descifra; con otro tenant NO.
    assert cripto_tenant.descifrar(material, empA) is not None
    assert cripto_tenant.descifrar(material, empB) is None
    assert C.proveedor_claves(empB) is None          # B no tiene certificado


def test_sustitucion_y_revocacion(db, fab, p12_valido):
    from src.services.fiscal import certificados as C
    blob, pw = p12_valido
    emp = fab.empresa("CERT SUST")
    fab.al_limpiar(lambda: _borra(db, emp))
    m1 = C.importar(blob, pw, id_empresa=emp, alias="c1")
    m2 = C.importar(blob, pw, id_empresa=emp, alias="c2")   # activar=True → desactiva c1
    activo = C.obtener_activo(emp)
    assert activo["id"] == m2["id"]
    # Reactivar el primero (sustitución).
    assert C.activar(m1["id"], emp) and C.obtener_activo(emp)["id"] == m1["id"]
    # Revocar el activo → ya no hay activo.
    assert C.revocar(m1["id"], emp)
    assert C.obtener_activo(emp) is None
    estados = {c["id"]: c["estado"] for c in C.listar(emp)}
    assert estados[m1["id"]] == "revocado"


def test_rotacion_recifra_material(db, fab, p12_valido):
    from src.services.fiscal import certificados as C
    blob, pw = p12_valido
    emp = fab.empresa("CERT ROT")
    fab.al_limpiar(lambda: _borra(db, emp))
    m = C.importar(blob, pw, id_empresa=emp)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT material_cifrado FROM fiscal_certificados WHERE id=%s", (m["id"],))
        antes = cur.fetchone()[0]
    n = C.rotar_cifrado(emp)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT material_cifrado FROM fiscal_certificados WHERE id=%s", (m["id"],))
        despues = cur.fetchone()[0]
    assert n == 1 and despues != antes               # re-cifrado (token nuevo)
    # Sigue descifrando correctamente tras la rotación.
    assert C.proveedor_claves(emp).disponible()


def test_certificado_caducado_no_activo(db, fab):
    from src.services.fiscal import certificados as C
    blob, pw = _p12(dias=-1)                          # ya caducado
    emp = fab.empresa("CERT CAD")
    fab.al_limpiar(lambda: _borra(db, emp))
    meta = C.importar(blob, pw, id_empresa=emp)
    assert meta["estado"] == "caducado"
    assert C.obtener_activo(emp) is None
