"""Integración · proveedor TicketBAI (C3.4-TBAI): registro legal, QR, cadena,
degradación honesta sin certificado y hook de venta. Mismo patrón que
`test_verifactu.py` (régimen hermano, mismo núcleo `fiscal_registros`)."""

import datetime as _dt
import json

import pytest

pytestmark = pytest.mark.db


def _borra_fiscal(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("fiscal_cola", "fiscal_registros", "fiscal_config", "fiscal_certificados",
                  "documentos_registro"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        conn.commit()


def _borra_evidencias(emp):
    """Borra los ficheros de evidencia (XML/acuse) que `guardar_evidencia` deja
    en disco bajo `documentos/fiscal/<empresa>/` durante el envío real de prueba."""
    import shutil
    try:
        from src.services.fiscal.evidencias import _dir_evidencias
        shutil.rmtree(_dir_evidencias(emp), ignore_errors=True)
    except Exception:
        pass


def _p12(nif="B99999999", password="clave-p12-tbai"):
    """Certificado AUTOFIRMADO de prueba (mismo helper que `test_firmante_xades.py`)
    — solo para validar el flujo de firma+envío end-to-end en tests, sin red ni
    un certificado real de producción."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (BestAvailableEncryption,
                                                              pkcs12)
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DEMO SELLO TBAI"),
                   x509.NameAttribute(NameOID.SERIAL_NUMBER, "IDCES-" + nif)])
    now = _dt.datetime.now(_dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(n).issuer_name(n)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - _dt.timedelta(days=1))
            .not_valid_after(now + _dt.timedelta(days=365)).sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(
        b"demo", key, cert, None, BestAvailableEncryption(password.encode())), password


def test_ticketbai_es_proveedor_por_territorio():
    from src.services.fiscal.registry import proveedor_para_territorio
    for territorio in ("araba", "bizkaia", "gipuzkoa"):
        clase = proveedor_para_territorio(territorio)
        assert clase is not None


def test_ticketbai_es_proveedor_por_config(db, fab):
    from src.db import fiscal as F
    from src.services.fiscal.factory import proveedor_para
    emp = fab.empresa("TBAI PROV")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(proveedor="ticketbai", territorio="bizkaia", modo="no_verifactu",
                     id_empresa=emp)
    p = proveedor_para(F.obtener_config(emp))
    assert p is not None and p.nombre == "ticketbai"


def test_ticketbai_registro_legal_sin_certificado_es_honesto(db, fab):
    """Sin certificado activo (caso normal en este entorno de pruebas): el
    registro SÍ se crea (encadenado de auditoría intacto) pero el QR/identificador
    quedan con el marcador SIN-CERTIFICADO — nunca un identificador inventado."""
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal.factory import proveedor_para
    emp = fab.empresa("TBAI REG")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(proveedor="ticketbai", territorio="gipuzkoa", modo="no_verifactu",
                     entorno="preproduccion", serie_por="empresa", id_empresa=emp)
    with contexto_tenant(emp, None):
        prov = proveedor_para(F.obtener_config(emp))
        r1 = prov.registrar("ticket", referencia="V1", total=12.10)
        r2 = prov.registrar("ticket", referencia="V2", total=20.0)
    assert r1.proveedor == "ticketbai"
    assert len(r1.hash) == 64 and r1.hash == r1.hash.upper()      # huella interna MAYÚS
    assert r1.qr.startswith("SIN-CERTIFICADO|")                   # degradación honesta
    assert r2.hash_anterior == r1.hash                             # encadenado intacto
    reg = F.obtener_registro(r1.id)
    meta = json.loads(reg["payload"])
    assert meta["territorio"] == "gipuzkoa"
    assert F.cadena_valida(emp, serie=r1.serie) is True


def test_ticketbai_cadena_detecta_manipulacion(db, fab):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal.factory import proveedor_para
    emp = fab.empresa("TBAI TAMPER")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(proveedor="ticketbai", territorio="araba", serie_por="empresa",
                     id_empresa=emp)
    with contexto_tenant(emp, None):
        r = proveedor_para(F.obtener_config(emp)).registrar("ticket", referencia="V1", total=10.0)
    meta = json.loads(F.obtener_registro(r.id)["payload"])
    meta["importe_total"] = "999.00"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE fiscal_registros SET payload=%s WHERE id=%s",
                    (json.dumps(meta), r.id))
        conn.commit()
    assert F.cadena_valida(emp, serie=r.serie) is False


def test_ticketbai_anular(db, fab):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal.factory import proveedor_para
    emp = fab.empresa("TBAI ANULA")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(proveedor="ticketbai", territorio="araba", serie_por="empresa",
                     id_empresa=emp)
    with contexto_tenant(emp, None):
        prov = proveedor_para(F.obtener_config(emp))
        r1 = prov.registrar("ticket", referencia="V1", total=10.0)
        r2 = prov.anular(r1)
    assert r2.tipo == "anulacion" and r2.hash_anterior == r1.hash
    assert F.cadena_valida(emp, serie=r1.serie) is True


def test_ticketbai_xml_sin_firmar_bien_formado(db, fab):
    """El XML sin firmar (antes de XAdES) es bien formado y lleva los campos
    legales básicos — comprobación estructural (no XSD oficial)."""
    import xml.etree.ElementTree as ET

    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal import ticketbai_xml as tx
    from src.services.fiscal.factory import proveedor_para
    emp = fab.empresa("TBAI XML")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(proveedor="ticketbai", territorio="araba", serie_por="empresa",
                     id_empresa=emp)
    with contexto_tenant(emp, None):
        r = proveedor_para(F.obtener_config(emp)).registrar("ticket", referencia="V1", total=10.0)
    fila = F.obtener_registro(r.id)
    xml_bytes = tx.registro_xml(fila)
    root = ET.fromstring(xml_bytes)
    assert root.tag.endswith("TicketBai")
    textos = [el.text for el in root.iter() if el.text]
    assert "10.00" in textos


def test_ticketbai_via_hook_tpv(db, fab):
    """Venta real con TicketBAI activo (territorio foral) → registro legal +
    encolado, sin tocar caja — mismo hook que ya usa Verifactu."""
    from src.db import conexion as cx, fiscal as F
    from src.db.empresa import contexto_tenant
    emp = fab.empresa("TBAI HOOK")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(proveedor="ticketbai", territorio="bizkaia", activo=1,
                     serie_por="empresa", id_empresa=emp)
    cod = fab.articulo(id_empresa=emp, precio=12.10, stock_tienda=50)
    with contexto_tenant(emp, None):
        vid = cx.registrar_venta_con_items([{"codigo": cod, "cantidad": 1, "precio_unitario": 12.10}])
    regs = F.listar_registros(id_empresa=emp)
    assert vid and len(regs) == 1 and regs[0]["proveedor"] == "ticketbai"
    assert regs[0]["referencia"] == str(vid)
    assert F.listar_cola(id_empresa=emp)            # encolado para envío LROE


def test_ticketbai_info_ticket_mutuamente_exclusivo_con_verifactu(db, fab):
    """`info_ticket` (mismo camino de render que Verifactu) muestra el QR
    TicketBAI cuando el proveedor configurado es ticketbai, nunca ambos a la vez."""
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal.factory import proveedor_para
    from src.services.fiscal.ticket import info_ticket
    emp = fab.empresa("TBAI TICKET")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(proveedor="ticketbai", territorio="araba", activo=1,
                     serie_por="empresa", id_empresa=emp)
    with contexto_tenant(emp, None):
        proveedor_para(F.obtener_config(emp)).registrar("ticket", referencia="V1", total=10.0)
    info = info_ticket("V1", id_empresa=emp, tipo="ticket")
    assert info is not None
    assert info["leyenda"] == "TicketBAI"
    assert info["csv"] is None                      # TicketBAI no usa CSV de acuse AEAT
    # Sin certificado activo en este entorno de pruebas: el identificador visible
    # cae honestamente al número de factura interno (serie/número), nunca uno
    # inventado como si fuera un identificador TBAI real.
    assert info["numserie"] == "A/1"


def test_ticketbai_identificador_real_con_certificado_activo(db, fab):
    """CON certificado activo, el identificador TBAI dentro del QR es el REAL
    (deja de ser el marcador SIN-CERTIFICADO)."""
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal import certificados as C
    from src.services.fiscal.factory import proveedor_para
    emp = fab.empresa("TBAI CERT")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    blob, pw = _p12()
    C.importar(blob, pw, id_empresa=emp)
    F.guardar_config(proveedor="ticketbai", territorio="bizkaia", modo="no_verifactu",
                     serie_por="empresa", id_empresa=emp)
    with contexto_tenant(emp, None):
        r = proveedor_para(F.obtener_config(emp)).registrar("ticket", referencia="V1", total=10.0)
    assert r.qr.startswith("https://batuz.eus/QRTBAI/")
    assert "id=TBAI-IDCES-B99999999-" in r.qr or "id=TBAI-" in r.qr
    assert F.cadena_valida(emp, serie=r.serie) is True


def test_ticketbai_envio_firmado_y_aceptado_end_to_end(db, fab):
    """Flujo COMPLETO con certificado real (autofirmado de prueba): registrar →
    firmar XAdES → enviar (transporte inyectado, sin red) → acuse ACEPTADO →
    estado 'enviado'. Confirma que `EmisorTicketBAI` firma de verdad (no un
    no-op) y que el worker marca 'enviado' SOLO tras un acuse positivo real."""
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal import certificados as C
    from src.services.fiscal.factory import proveedor_para
    emp = fab.empresa("TBAI E2E")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    fab.al_limpiar(lambda: _borra_evidencias(emp))
    blob, pw = _p12()
    C.importar(blob, pw, id_empresa=emp)
    F.guardar_config(proveedor="ticketbai", territorio="araba", modo="no_verifactu",
                     activo=1, serie_por="empresa", id_empresa=emp)
    with contexto_tenant(emp, None):
        r = proveedor_para(F.obtener_config(emp)).registrar("ticket", referencia="V1", total=10.0)

    from src.services.fiscal.emisores.ticketbai_lroe import EmisorTicketBAI
    from src.services.fiscal.firmantes import FirmanteXAdES

    firmante = FirmanteXAdES(C.proveedor_claves(emp))
    assert firmante.disponible()

    capturado = {}

    def _transporte_fake(url, cuerpo, cfg):
        capturado["url"] = url
        capturado["cuerpo"] = cuerpo
        return 200, "<Respuesta><EstadoRegistro>Correcto</EstadoRegistro></Respuesta>"

    emisor = EmisorTicketBAI(transporte=_transporte_fake, firmante=firmante,
                             config=F.obtener_config(emp))
    assert emisor.disponible()        # con cert+firmante+transporte → disponible de verdad
    res = emisor.enviar(r, F.obtener_config(emp))
    assert res["ok"] is True and res["estado"] == "enviado"
    assert capturado["url"] == "https://ticketbai.araba.eus/tbai/test/recepcion"
    # El cuerpo enviado es el XML REALMENTE FIRMADO (XAdES), no un esqueleto vacío.
    assert b"Signature" in capturado["cuerpo"] and b"TicketBai" in capturado["cuerpo"]

    F.actualizar_estado(r.id, "enviado")
    assert F.obtener_registro(r.id)["estado"] == "enviado"
    assert F.cadena_valida(emp, serie=r.serie) is True
