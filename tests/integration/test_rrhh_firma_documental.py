"""
F4.11 · Firma / aceptación documental RRHH.

Marcar requiere firma, aceptar/rechazar, estados, trazabilidad (auditoría),
inmutabilidad (hash/ref/estado), seguridad (solo propios), expiración, integración con
portal/expediente, multiempresa.
"""

import pytest

pytestmark = pytest.mark.db

from src.rrhh.db import documentos as D, empleados as E
from src.rrhh import firma_servicio as F
from src.rrhh.firma_servicio import FirmaError


def _limpia(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rrhh_empleados WHERE id_empresa=%s", (emp,))   # cascada docs/auditoría
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _emp(db, fab, nif="65000001A", id_usuario=6001):
    emp = fab.empresa("F411")
    fab.al_limpiar(lambda: _limpia(db, emp))
    eid = E.crear_empleado(id_empresa=emp, nombre="Ana", nif=nif, id_usuario=id_usuario)
    return emp, eid


def _doc(emp, eid, tipo="contrato", ref="x.pdf"):
    return D.crear_documento(eid, emp, tipo_doc=tipo, ref_documento=ref, fecha="2026-06-01")


# ── Marcar + aceptar ──────────────────────────────────────────────────────────
def test_marcar_y_aceptar(db, fab):
    emp, eid = _emp(db, fab)
    did = _doc(emp, eid)
    assert F.marcar_requiere_firma(did, id_empresa=emp)
    pend = F.listar_pendientes(eid, emp)
    assert len(pend) == 1 and pend[0]["estado_firma"] == "pendiente"
    assert F.aceptar(did, usuario="ana", id_empleado=eid, ip="10.0.0.1", id_empresa=emp)
    d = D.obtener_documento(did, emp)
    assert d["estado_firma"] == "aceptado" and d["fecha_aceptacion"] is not None
    assert F.listar_pendientes(eid, emp) == []


def test_rechazar(db, fab):
    emp, eid = _emp(db, fab)
    did = _doc(emp, eid, tipo="carta_despido")
    F.marcar_requiere_firma(did, id_empresa=emp)
    assert F.rechazar(did, usuario="ana", id_empleado=eid, motivo="no conforme", id_empresa=emp)
    assert D.obtener_documento(did, emp)["estado_firma"] == "rechazado"


# ── Trazabilidad / auditoría ──────────────────────────────────────────────────
def test_auditoria(db, fab):
    emp, eid = _emp(db, fab)
    did = _doc(emp, eid)
    F.marcar_requiere_firma(did, id_empresa=emp)
    F.aceptar(did, usuario="ana", id_empleado=eid, ip="1.2.3.4", id_empresa=emp)
    hist = F.historial(did, emp)
    acciones = [h["accion"] for h in hist]
    assert "requiere_firma" in acciones and "aceptado" in acciones
    acept = [h for h in hist if h["accion"] == "aceptado"][0]
    assert acept["usuario"] == "ana" and acept["ip"] == "1.2.3.4" and acept["id_empleado"] == eid


# ── Inmutabilidad ──────────────────────────────────────────────────────────────
def test_no_reaceptar(db, fab):
    emp, eid = _emp(db, fab)
    did = _doc(emp, eid)
    F.marcar_requiere_firma(did, id_empresa=emp)
    F.aceptar(did, id_empleado=eid, id_empresa=emp)
    with pytest.raises(FirmaError, match="ya está"):
        F.aceptar(did, id_empleado=eid, id_empresa=emp)
    with pytest.raises(FirmaError):
        F.rechazar(did, id_empleado=eid, id_empresa=emp)


def test_hash_y_ref_se_conservan(db, fab):
    emp, eid = _emp(db, fab, nif="65000009Z")
    did = _doc(emp, eid, ref="conserva.pdf")
    F.marcar_requiere_firma(did, id_empresa=emp)
    antes = D.obtener_documento(did, emp)
    F.aceptar(did, id_empleado=eid, id_empresa=emp)
    despues = D.obtener_documento(did, emp)
    assert despues["ref_documento"] == antes["ref_documento"] == "conserva.pdf"
    assert despues["hash_documental"] == antes["hash_documental"]   # hash no cambia


# ── Seguridad ──────────────────────────────────────────────────────────────────
def test_no_firmar_documento_ajeno(db, fab):
    emp, e1 = _emp(db, fab, nif="65100001A", id_usuario=6101)
    e2 = E.crear_empleado(id_empresa=emp, nombre="Leo", nif="65100002B", id_usuario=6102)
    did = _doc(emp, e1)
    F.marcar_requiere_firma(did, id_empresa=emp)
    with pytest.raises(FirmaError, match="otro empleado"):
        F.aceptar(did, id_empleado=e2, id_empresa=emp)   # e2 no puede firmar doc de e1
    assert D.obtener_documento(did, emp)["estado_firma"] == "pendiente"


def test_documento_no_firmable(db, fab):
    emp, eid = _emp(db, fab, nif="65000003C")
    did = _doc(emp, eid)            # NO marcado requiere_firma
    with pytest.raises(FirmaError, match="no requiere firma"):
        F.aceptar(did, id_empleado=eid, id_empresa=emp)


# ── Expiración ──────────────────────────────────────────────────────────────
def test_expiracion(db, fab):
    emp, eid = _emp(db, fab, nif="65000004D")
    did = _doc(emp, eid)
    F.marcar_requiere_firma(did, expira="2020-01-01", id_empresa=emp)   # ya vencido
    n = F.expirar_pendientes(emp)
    assert n == 1 and D.obtener_documento(did, emp)["estado_firma"] == "expirado"


# ── Portal + expediente ──────────────────────────────────────────────────────
def test_portal_acepta_solo_propios(db, fab):
    from src.rrhh import portal_servicio as PS
    emp, e1 = _emp(db, fab, nif="65200001A", id_usuario=6201)
    e2 = E.crear_empleado(id_empresa=emp, nombre="Leo", nif="65200002B", id_usuario=6202)
    d1 = _doc(emp, e1); d2 = _doc(emp, e2)
    F.marcar_requiere_firma(d1, id_empresa=emp); F.marcar_requiere_firma(d2, id_empresa=emp)
    # e1 solo ve sus pendientes
    assert [d["id"] for d in PS.documentos_pendientes(e1, emp)] == [d1]
    # e1 no puede aceptar el de e2
    with pytest.raises(FirmaError):
        PS.aceptar_documento(e1, d2, usuario="ana", id_empresa=emp)
    assert PS.aceptar_documento(e1, d1, usuario="ana", id_empresa=emp)


def test_expediente_muestra_estado(db, fab):
    emp, eid = _emp(db, fab, nif="65000005E")
    did = _doc(emp, eid)
    F.marcar_requiere_firma(did, id_empresa=emp)
    F.aceptar(did, id_empleado=eid, id_empresa=emp)
    exp = E.expediente(eid, emp)
    doc = [d for d in exp["documentos"] if d["id"] == did][0]
    assert doc["estado_firma"] == "aceptado"


# ── Multiempresa ─────────────────────────────────────────────────────────────
def test_multiempresa(db, fab):
    emp1, e1 = _emp(db, fab, nif="65300001A", id_usuario=6301)
    emp2 = fab.empresa("F411 B"); fab.al_limpiar(lambda: _limpia(db, emp2))
    e2 = E.crear_empleado(id_empresa=emp2, nombre="Leo", nif="65300002B")
    d1 = _doc(emp1, e1)
    F.marcar_requiere_firma(d1, id_empresa=emp1)
    assert len(F.listar_pendientes(e1, emp1)) == 1
    # desde emp2 no se ve ni se puede tocar
    assert F.listar_pendientes(e2, emp2) == []
    with pytest.raises(FirmaError):
        F.aceptar(d1, id_empleado=e2, id_empresa=emp2)


# ── GUI portal ───────────────────────────────────────────────────────────────
def test_portal_gui_pendientes(db, fab, monkeypatch):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    emp, eid = _emp(db, fab, nif="65400001F", id_usuario=6401)
    did = _doc(emp, eid)
    F.marcar_requiere_firma(did, id_empresa=emp)
    from src.db.empresa import contexto_tenant
    with contexto_tenant(emp, None):
        from src.gui.portal_empleado import PortalEmpleadoWindow
        w = PortalEmpleadoWindow(usuario={"id": 6401, "nombre": "ana", "perfil": "OPERARIO"})
        assert w.tbl_pend.rowCount() == 1
        w.close()
