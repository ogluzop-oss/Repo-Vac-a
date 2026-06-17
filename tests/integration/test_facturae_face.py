"""Integración · servicio Facturae + canal FACe (C3.4.4) con transporte simulado."""

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


def _empresa_nif(db, fab, nombre):
    emp = fab.empresa(nombre)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE empresas SET razon_social=%s, cif_nif=%s, direccion_fiscal=%s, "
                    "cp=%s, municipio=%s, provincia=%s WHERE id_empresa=%s",
                    (nombre, "A12345674", "Calle Emisor 1", "28001", "Madrid", "Madrid", emp))
        conn.commit()
    return emp


def _venta(db, emp, nif_cliente="B12345678"):
    fecha = "2026-06-16 10:00:00"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO ventas (fecha, total, forma_pago, id_empresa, cliente_nif) "
                    "VALUES (%s,%s,'factura',%s,%s)", (fecha, 12.10, emp, nif_cliente))
        vid = cur.lastrowid
        cur.execute("INSERT INTO venta_items (venta_id, codigo_articulo, nombre, cantidad, "
                    "precio_unitario, subtotal, id_empresa) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (vid, "ART1", "Producto X", 1, 12.10, 12.10, emp))
        conn.commit()
    return vid


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("facturae_envios", "facturae_destinatarios", "fiscal_certificados",
                  "venta_items", "ventas", "documentos_registro", "empresas"):
            col = "id_empresa"
            cur.execute(f"DELETE FROM {t} WHERE {col}=%s", (emp,))
        conn.commit()


def _destinatario(emp, nif="B12345678"):
    from src.services.fiscal.facturae import destinatarios as D
    D.guardar(nif, id_empresa=emp, razon_social="CLIENTE SL", tipo_persona="J",
              direccion="Calle Cliente 2", cp="08001", municipio="Barcelona",
              provincia="Barcelona", es_aapp=0)


def test_generar_facturae_encola_y_evidencia(db, fab):
    from src.services.fiscal import certificados as C
    from src.services.fiscal.facturae import envios, servicio
    from src.db.empresa import contexto_tenant
    blob, pw = _p12()
    emp = _empresa_nif(db, fab, "FE GEN")
    fab.al_limpiar(lambda: _borra(db, emp))
    C.importar(blob, pw, id_empresa=emp)
    _destinatario(emp)
    vid = _venta(db, emp)
    with contexto_tenant(emp, None):
        r = servicio.generar_facturae(vid, id_empresa=emp)
    assert r["ok"] and r["envio_id"]
    assert envios.listar("pendiente", id_empresa=emp)[0]["venta_id"] == vid


def test_envio_face_correcto(db, fab):
    from src.services.fiscal import certificados as C
    from src.services.fiscal.facturae import envios, servicio
    from src.services.fiscal.facturae.emisores.face import CanalFACe
    from src.db.empresa import contexto_tenant
    blob, pw = _p12()
    emp = _empresa_nif(db, fab, "FE ENVIO")
    fab.al_limpiar(lambda: _borra(db, emp))
    C.importar(blob, pw, id_empresa=emp)
    _destinatario(emp)
    vid = _venta(db, emp)
    with contexto_tenant(emp, None):
        servicio.generar_facturae(vid, id_empresa=emp)

    enviado = {}
    def transporte(url, cuerpo, cfg):
        enviado["cuerpo"] = cuerpo
        return 200, "<resultado><codigo>0</codigo><numeroRegistro>FACE-123</numeroRegistro></resultado>"

    res = servicio.procesar_envios_facturae(id_empresa=emp, canal=CanalFACe(transporte=transporte))
    assert res["enviados"] == 1
    env = envios.listar("enviado", id_empresa=emp)
    assert env and env[0]["numero_registro"] == "FACE-123"
    assert b"registrarFactura" in enviado["cuerpo"] and b"soapenv:Body" in enviado["cuerpo"]


def test_generar_sin_destinatario_falla_claramente(db, fab):
    from src.services.fiscal import certificados as C
    from src.services.fiscal.facturae import servicio
    from src.db.empresa import contexto_tenant
    blob, pw = _p12()
    emp = _empresa_nif(db, fab, "FE SIN DEST")
    fab.al_limpiar(lambda: _borra(db, emp))
    C.importar(blob, pw, id_empresa=emp)
    vid = _venta(db, emp, nif_cliente="B99999999")        # sin destinatario configurado
    with contexto_tenant(emp, None):
        r = servicio.generar_facturae(vid, id_empresa=emp)
    assert r["ok"] is False and "receptor" in r["error"].lower()


def test_envio_sin_certificado_espera(db, fab):
    from src.services.fiscal.facturae import envios, servicio
    from src.db.empresa import contexto_tenant
    emp = _empresa_nif(db, fab, "FE NO CERT")
    fab.al_limpiar(lambda: _borra(db, emp))
    _destinatario(emp)
    vid = _venta(db, emp)
    # Crea el envío directamente (sin firmar) para probar la cola sin certificado.
    envios.crear(vid, str(vid), id_empresa=emp)
    res = servicio.procesar_envios_facturae(id_empresa=emp)   # canal real, no disponible
    assert res["enviados"] == 0 and res["en_espera"] == 1
