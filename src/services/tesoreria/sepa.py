"""
SEPA — generación de ficheros XML ISO 20022 (rama Tesorería, FASE 9).

Construye remesas de transferencias (pain.001.001.03) y de adeudos directos (pain.008.001.02)
a partir de los datos persistidos en src/db/sepa.py, y valida el XML contra los XSD
(esquemas/) con lxml — mismo patrón que Verifactu/Facturae. Reutiliza la cuenta de la empresa
(IBAN descifrado) como ordenante/acreedor.
"""

import datetime as _dt
import logging
import os
import uuid
import xml.etree.ElementTree as ET

from src.db import sepa as _S
from src.db import tesoreria as _T
from src.db.conexion import EMPRESA_DEFAULT_ID

logger = logging.getLogger("sepa_svc")

NS_001 = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
NS_008 = "urn:iso:std:iso:20022:tech:xsd:pain.008.001.02"


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _e(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    if text is not None:
        el.text = str(text)
    return el


def _ruta_xsd(nombre):
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        from src.utils.recursos import ruta_recurso, es_frozen
        if es_frozen():
            return ruta_recurso("src", "services", "tesoreria", "esquemas", nombre)
    except Exception:
        pass
    return os.path.join(base, "esquemas", nombre)


def validar_xsd(xml_bytes, xsd_nombre) -> tuple:
    """(ok, errores) contra el XSD. Si lxml no está, (True, 'lxml-ausente') para no bloquear."""
    try:
        from lxml import etree
    except Exception:
        return True, "lxml-ausente"
    try:
        sch = etree.XMLSchema(etree.parse(_ruta_xsd(xsd_nombre)))
        doc = etree.fromstring(xml_bytes if isinstance(xml_bytes, bytes) else xml_bytes.encode("utf-8"))
        ok = sch.validate(doc)
        return ok, ("" if ok else str(sch.error_log))
    except Exception as e:
        return False, str(e)


def _datos_ordenante(id_empresa, id_cuenta):
    """Nombre, IBAN (claro) y BIC de la cuenta de la empresa que ordena/cobra."""
    cuenta = _T.obtener_cuenta(id_cuenta, descifrar=True, id_empresa=id_empresa) if id_cuenta else None
    nombre = "EMPRESA"
    try:
        from src.db.empresa import obtener_empresa
        emp = obtener_empresa(id_empresa) or {}
        nombre = emp.get("nombre_empresa") or emp.get("nombre") or nombre
    except Exception:
        pass
    if cuenta:
        return {"nombre": cuenta.get("titular") or nombre,
                "iban": (cuenta.get("iban") or "").replace(" ", ""),
                "bic": cuenta.get("bic") or ""}
    return {"nombre": nombre, "iban": "", "bic": ""}


def generar_xml(id_remesa, *, id_empresa=None) -> dict:
    """Genera y valida el XML de la remesa. Lo persiste y pasa la remesa a 'emitida'.
    Devuelve {ok, xsd_ok, mensaje_id, xml, errores}."""
    id_empresa = _emp(id_empresa)
    try:
        from src.services import autorizacion
        autorizacion.exigir(None, "tesoreria.remesas.generar")
    except ImportError:
        pass
    rem = _S.obtener_remesa(id_remesa, id_empresa)
    if not rem:
        return {"ok": False, "errores": "remesa no encontrada"}
    # Idempotencia / anti doble-emisión: si ya tiene XML emitido, NO se regenera (evita un
    # nuevo MsgId y una segunda remesa con el mismo contenido). Solo se (re)genera en borrador.
    if rem.get("estado") in ("emitida", "aceptada", "ejecutada") and rem.get("fichero_xml"):
        return {"ok": True, "xsd_ok": True, "mensaje_id": rem.get("mensaje_id"),
                "xml": rem["fichero_xml"], "errores": "", "idempotente": True}
    if rem.get("estado") not in ("borrador", "rechazada"):
        return {"ok": False, "errores": f"estado no permite generar: {rem.get('estado')}"}
    lineas = _S.lineas_remesa(id_remesa, id_empresa)
    if not lineas:
        return {"ok": False, "errores": "remesa sin operaciones"}
    ordenante = _datos_ordenante(id_empresa, rem.get("id_cuenta"))
    msg_id = "MSG" + uuid.uuid4().hex[:20]
    ahora = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    total = round(sum(float(x["importe"]) for x in lineas), 2)
    n = len(lineas)
    if rem["tipo"] == "TRANSFER":
        xml_bytes = _xml_pain001(msg_id, ahora, ordenante, lineas, total, n)
        xsd = "pain.001.001.03.xsd"
    else:
        xml_bytes = _xml_pain008(msg_id, ahora, ordenante, lineas, total, n, id_empresa)
        xsd = "pain.008.001.02.xsd"
    ok_xsd, err = validar_xsd(xml_bytes, xsd)
    xml_texto = xml_bytes.decode("utf-8")
    if ok_xsd:
        _S.guardar_xml(id_remesa, msg_id, xml_texto, id_empresa)
    return {"ok": ok_xsd, "xsd_ok": ok_xsd, "mensaje_id": msg_id,
            "xml": xml_texto, "errores": err}


def _xml_pain001(msg_id, ahora, ordenante, lineas, total, n):
    ET.register_namespace("", NS_001)
    root = ET.Element(f"{{{NS_001}}}Document")
    cti = _e(root, f"{{{NS_001}}}CstmrCdtTrfInitn")
    gh = _e(cti, f"{{{NS_001}}}GrpHdr")
    _e(gh, f"{{{NS_001}}}MsgId", msg_id)
    _e(gh, f"{{{NS_001}}}CreDtTm", ahora)
    _e(gh, f"{{{NS_001}}}NbOfTxs", n)
    _e(gh, f"{{{NS_001}}}CtrlSum", f"{total:.2f}")
    _e(_e(gh, f"{{{NS_001}}}InitgPty"), f"{{{NS_001}}}Nm", ordenante["nombre"])
    pmt = _e(cti, f"{{{NS_001}}}PmtInf")
    _e(pmt, f"{{{NS_001}}}PmtInfId", "PMT" + uuid.uuid4().hex[:18])
    _e(pmt, f"{{{NS_001}}}PmtMtd", "TRF")
    _e(pmt, f"{{{NS_001}}}NbOfTxs", n)
    _e(pmt, f"{{{NS_001}}}CtrlSum", f"{total:.2f}")
    _e(pmt, f"{{{NS_001}}}ReqdExctnDt", _dt.date.today().strftime("%Y-%m-%d"))
    _e(_e(pmt, f"{{{NS_001}}}Dbtr"), f"{{{NS_001}}}Nm", ordenante["nombre"])
    _e(_e(_e(pmt, f"{{{NS_001}}}DbtrAcct"), f"{{{NS_001}}}Id"), f"{{{NS_001}}}IBAN", ordenante["iban"])
    _e(_e(_e(pmt, f"{{{NS_001}}}DbtrAgt"), f"{{{NS_001}}}FinInstnId"),
       f"{{{NS_001}}}BIC", ordenante["bic"] or "NOTPROVIDED")
    for ln in lineas:
        tx = _e(pmt, f"{{{NS_001}}}CdtTrfTxInf")
        _e(_e(tx, f"{{{NS_001}}}PmtId"), f"{{{NS_001}}}EndToEndId", ln["end_to_end_id"])
        _e(_e(tx, f"{{{NS_001}}}Amt"), f"{{{NS_001}}}InstdAmt", f"{float(ln['importe']):.2f}", Ccy="EUR")
        if ln.get("bic"):
            _e(_e(_e(tx, f"{{{NS_001}}}CdtrAgt"), f"{{{NS_001}}}FinInstnId"), f"{{{NS_001}}}BIC", ln["bic"])
        _e(_e(tx, f"{{{NS_001}}}Cdtr"), f"{{{NS_001}}}Nm", ln.get("nombre_tercero") or "BENEFICIARIO")
        _e(_e(_e(tx, f"{{{NS_001}}}CdtrAcct"), f"{{{NS_001}}}Id"), f"{{{NS_001}}}IBAN", ln["iban"])
        _e(_e(tx, f"{{{NS_001}}}RmtInf"), f"{{{NS_001}}}Ustrd", (ln.get("concepto") or "Pago")[:140])
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _xml_pain008(msg_id, ahora, acreedor, lineas, total, n, id_empresa):
    ET.register_namespace("", NS_008)
    root = ET.Element(f"{{{NS_008}}}Document")
    ddi = _e(root, f"{{{NS_008}}}CstmrDrctDbtInitn")
    gh = _e(ddi, f"{{{NS_008}}}GrpHdr")
    _e(gh, f"{{{NS_008}}}MsgId", msg_id)
    _e(gh, f"{{{NS_008}}}CreDtTm", ahora)
    _e(gh, f"{{{NS_008}}}NbOfTxs", n)
    _e(gh, f"{{{NS_008}}}CtrlSum", f"{total:.2f}")
    _e(_e(gh, f"{{{NS_008}}}InitgPty"), f"{{{NS_008}}}Nm", acreedor["nombre"])
    pmt = _e(ddi, f"{{{NS_008}}}PmtInf")
    _e(pmt, f"{{{NS_008}}}PmtInfId", "PMT" + uuid.uuid4().hex[:18])
    _e(pmt, f"{{{NS_008}}}PmtMtd", "DD")
    _e(pmt, f"{{{NS_008}}}NbOfTxs", n)
    _e(pmt, f"{{{NS_008}}}CtrlSum", f"{total:.2f}")
    _e(pmt, f"{{{NS_008}}}ReqdColltnDt", _dt.date.today().strftime("%Y-%m-%d"))
    _e(_e(pmt, f"{{{NS_008}}}Cdtr"), f"{{{NS_008}}}Nm", acreedor["nombre"])
    _e(_e(_e(pmt, f"{{{NS_008}}}CdtrAcct"), f"{{{NS_008}}}Id"), f"{{{NS_008}}}IBAN", acreedor["iban"])
    _e(_e(_e(pmt, f"{{{NS_008}}}CdtrAgt"), f"{{{NS_008}}}FinInstnId"),
       f"{{{NS_008}}}BIC", acreedor["bic"] or "NOTPROVIDED")
    for ln in lineas:
        tx = _e(pmt, f"{{{NS_008}}}DrctDbtTxInf")
        _e(_e(tx, f"{{{NS_008}}}PmtId"), f"{{{NS_008}}}EndToEndId", ln["end_to_end_id"])
        _e(tx, f"{{{NS_008}}}InstdAmt", f"{float(ln['importe']):.2f}", Ccy="EUR")
        mandato = _S.obtener_mandato(ln["id_mandato"], descifrar=True, id_empresa=id_empresa) if ln.get("id_mandato") else None
        mri = _e(_e(tx, f"{{{NS_008}}}DrctDbtTx"), f"{{{NS_008}}}MndtRltdInf")
        _e(mri, f"{{{NS_008}}}MndtId", (mandato or {}).get("referencia_mandato") or "MNDT-NA")
        _e(mri, f"{{{NS_008}}}DtOfSgntr",
           str((mandato or {}).get("fecha_firma") or _dt.date.today().strftime("%Y-%m-%d"))[:10])
        if ln.get("bic"):
            _e(_e(_e(tx, f"{{{NS_008}}}DbtrAgt"), f"{{{NS_008}}}FinInstnId"), f"{{{NS_008}}}BIC", ln["bic"])
        _e(_e(tx, f"{{{NS_008}}}Dbtr"), f"{{{NS_008}}}Nm", ln.get("nombre_tercero") or "DEUDOR")
        _e(_e(_e(tx, f"{{{NS_008}}}DbtrAcct"), f"{{{NS_008}}}Id"), f"{{{NS_008}}}IBAN", ln["iban"])
        _e(_e(tx, f"{{{NS_008}}}RmtInf"), f"{{{NS_008}}}Ustrd", (ln.get("concepto") or "Adeudo")[:140])
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
