"""
F4.2.1 · Cableado de generadores RRHH → expediente laboral.

Genera documentos (PDF real) con un empleado existente y verifica la traza persistente
en rrhh_documentos + las tablas especializadas (contratos/nóminas/vacaciones/ausencias),
el snapshot, la no-creación implícita de empleados y que el PDF se sigue generando.
"""

import json
import os

import pytest

pytestmark = pytest.mark.db

from src.rrhh.db import (ausencias as A, contratos as C, documentos as D,
                         empleados as E, nominas as N, vacaciones as V)

_NIF = "55667788X"


def _app():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    return QApplication.instance() or QApplication([])


def _limpia(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rrhh_empleados WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _entorno(db, fab):
    """Empresa + tenant activo + empleado con NIF conocido. Devuelve (emp, eid)."""
    from src.db import empresa as empmod
    emp = fab.empresa("F421")
    fab.al_limpiar(lambda: _limpia(db, emp))
    # Forzar tenant activo = empresa de prueba (el hook usa empresa_actual_id()).
    ctx = empmod.contexto_tenant(emp, None)
    ctx.__enter__()
    fab.al_limpiar(lambda: ctx.__exit__(None, None, None))
    eid = E.crear_empleado(id_empresa=emp, nombre="Ana", apellidos="Ruiz", nif=_NIF)
    return emp, eid


def _genera(tipo, datos):
    import src.gui.gestion_usuarios as gu
    w = gu._WizardDocumentoFiscal()
    w._tipo = tipo
    w._datos = dict(datos)
    w._generar_pdf()
    ruta = getattr(w, "_pdf_ruta", None)
    return ruta


def _base(**kw):
    d = dict(trabajador="Ana Ruiz", nif=_NIF, fecha="10/06/2026", subtipo="INDEFINIDO")
    d.update(kw)
    return d


def test_documento_generico_persiste_y_snapshot(db, fab):
    _app(); emp, eid = _entorno(db, fab)
    ruta = _genera("CERTIFICADO", _base(subtipo="EMPRESA"))
    assert ruta and os.path.exists(ruta)
    fab.al_limpiar(lambda r=ruta: os.path.exists(r) and os.remove(r))
    docs = D.listar_documentos(eid, emp)
    assert len(docs) == 1 and docs[0]["tipo_doc"] == "certificado"
    assert docs[0]["ref_documento"] == ruta
    snap = json.loads(docs[0]["datos_snapshot"])
    assert snap["nif"] == _NIF and snap["subtipo"] == "EMPRESA"


def test_contrato_alimenta_rrhh_contratos(db, fab):
    _app(); emp, eid = _entorno(db, fab)
    _genera("CONTRATO", _base(subtipo="TEMPORAL", salario="1500", fecha_fin="31/12/2026",
                              tipo_jornada="completa"))
    ctr = C.listar_contratos(eid, emp)
    assert len(ctr) == 1 and ctr[0]["modalidad"] == "TEMPORAL"
    assert float(ctr[0]["salario"]) == 1500.0
    assert str(ctr[0]["fecha_inicio"]) == "2026-06-10" and str(ctr[0]["fecha_fin"]) == "2026-12-31"
    assert len(D.listar_documentos(eid, emp, tipo_doc="contrato")) == 1


def test_nomina_alimenta_rrhh_nominas(db, fab):
    """F4.3.4: la persistencia guarda EXACTAMENTE el resultado del motor único
    (sin recalcular). Se compara contra el motor con los mismos datos."""
    from src.rrhh.nomina_servicio import calcular_desde_datos
    _app(); emp, eid = _entorno(db, fab)
    datos = _base(salario="2000", num_pagas="14", irpf_pct="15", plus_convenio="50",
                  grupo_cotizacion="1")
    res = calcular_desde_datos(datos)              # fuente de verdad
    _genera("NÓMINA", datos)
    noms = N.listar_nominas(eid, emp)
    assert len(noms) == 1
    n = noms[0]
    assert n["anio"] == 2026 and n["mes"] == 6
    assert float(n["base"]) == res.bccc            # BCCC del motor
    assert float(n["bruto"]) == res.total_devengado
    assert float(n["irpf_importe"]) == res.irpf_importe
    assert float(n["ss_importe"]) == res.ss_trabajador["total"]
    assert float(n["neto"]) == res.liquido
    assert n["conceptos"] and "devengos" in n["conceptos"]   # snapshot completo


def test_vacaciones_alimenta_rrhh_vacaciones(db, fab):
    _app(); emp, eid = _entorno(db, fab)
    _genera("VACACIONES", _base(subtipo="APROBACIÓN", fecha="01/07/2026",
                                fecha_fin_vac="15/07/2026", responsable="Jefe"))
    vac = V.listar_vacaciones(eid, emp)
    assert len(vac) == 1
    assert vac[0]["tipo"] == "aprobacion" and vac[0]["estado"] == "aprobada"
    assert float(vac[0]["dias"]) == 15.0


def test_baja_alimenta_rrhh_ausencias(db, fab):
    _app(); emp, eid = _entorno(db, fab)
    _genera("BAJA", _base(subtipo="DESPIDO", motivo_baja="reorganización"))
    aus = A.listar_ausencias(eid, emp)
    assert len(aus) == 1 and aus[0]["motivo"] == "reorganización"


def test_sin_empleado_no_persiste_ni_crea(db, fab):
    """NIF sin expediente → no se persiste documento ni se crea empleado (PDF intacto)."""
    _app(); emp, eid = _entorno(db, fab)
    ruta = _genera("CERTIFICADO", _base(nif="99999999R"))   # NIF inexistente
    assert ruta and os.path.exists(ruta)                     # PDF sí se genera
    fab.al_limpiar(lambda r=ruta: os.path.exists(r) and os.remove(r))
    assert E.obtener_por_nif("99999999R", emp) is None       # no se creó empleado
    assert len(D.listar_documentos(eid, emp)) == 0           # no se persistió documento


def test_no_duplica_en_dos_generaciones(db, fab):
    _app(); emp, eid = _entorno(db, fab)
    _genera("CERTIFICADO", _base(subtipo="EMPRESA"))
    _genera("CERTIFICADO", _base(subtipo="EMPRESA"))
    docs = D.listar_documentos(eid, emp)
    assert len(docs) == 2                                     # 2 generaciones → 2 trazas (1 c/u)
