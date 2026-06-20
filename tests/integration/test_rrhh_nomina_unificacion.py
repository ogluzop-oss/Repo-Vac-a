"""
F4.3.4 · Unificación del motor de nómina.

Verifica que render y persistencia consumen el MISMO motor (única fuente de cálculo),
que no recalculan, la coherencia PDF↔BD y la compatibilidad con el expediente.
"""

import inspect
import json

import pytest

pytestmark = pytest.mark.db

from src.rrhh.db import empleados as E, nominas as N
from src.rrhh.nomina_servicio import calcular_desde_datos

_NIF = "11223344A"


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
    from src.db import empresa as empmod
    emp = fab.empresa("F434")
    fab.al_limpiar(lambda: _limpia(db, emp))
    ctx = empmod.contexto_tenant(emp, None); ctx.__enter__()
    fab.al_limpiar(lambda: ctx.__exit__(None, None, None))
    eid = E.crear_empleado(id_empresa=emp, nombre="Eva", apellidos="Sanz", nif=_NIF)
    return emp, eid


_DATOS = dict(trabajador="Eva Sanz", nif=_NIF, fecha="10/06/2026", subtipo="INDEFINIDO",
              salario="2100", num_pagas="14", irpf_pct="16", plus_convenio="40",
              nocturnidad="20", grupo_cotizacion="1")


# 1/3. render_nomina NO calcula (delega en el servicio; sin aritmética de SS/IRPF/neto)
def test_render_no_calcula():
    import sys
    import src.rrhh.documents.render.render_nomina  # noqa: F401 (asegura import del módulo)
    mod = sys.modules["src.rrhh.documents.render.render_nomina"]   # evita shadowing del __init__
    src = inspect.getsource(mod)
    assert "calcular_desde_datos" in src
    for prohibido in ("irpf_ret", "ss_ret", "bruto_total = round", "neto =", "* irpf_pct", "* ss_emp_pct"):
        assert prohibido not in src, f"render aún calcula: {prohibido}"


# 2/3. persistencia NO calcula la nómina (usa el servicio)
def test_persistencia_no_calcula():
    import src.rrhh.persistencia as PS
    src = inspect.getsource(PS._registrar_nomina)
    assert "calcular_desde_datos" in src
    for prohibido in ("base * irpf_pct", "base * ss_pct", "bruto - irpf", "salario / num_pagas"):
        assert prohibido not in src


# 4/5/6. PDF generado + persistencia + coherencia PDF↔BD (mismo motor)
def test_coherencia_pdf_bd(db, fab):
    _app(); emp, eid = _entorno(db, fab)
    import src.gui.gestion_usuarios as gu
    w = gu._WizardDocumentoFiscal(); w._tipo = "NÓMINA"; w._datos = dict(_DATOS)
    w._generar_pdf()
    assert getattr(w, "_pdf_ruta", None)            # PDF generado
    import os
    fab.al_limpiar(lambda r=w._pdf_ruta: os.path.exists(r) and os.remove(r))
    res = calcular_desde_datos(_DATOS)               # fuente de verdad (mismo cálculo del render)
    noms = N.listar_nominas(eid, emp)
    assert len(noms) == 1
    n = noms[0]
    # BD coincide con el motor → render y persistencia comparten resultado
    assert float(n["bruto"]) == res.total_devengado
    assert float(n["base"]) == res.bccc
    assert float(n["irpf_importe"]) == res.irpf_importe
    assert float(n["ss_importe"]) == res.ss_trabajador["total"]
    assert float(n["neto"]) == res.liquido


# 7. Snapshot completo en el expediente (devengos/deducciones/bases/contingencias)
def test_snapshot_completo(db, fab):
    _app(); emp, eid = _entorno(db, fab)
    import src.gui.gestion_usuarios as gu
    w = gu._WizardDocumentoFiscal(); w._tipo = "NÓMINA"; w._datos = dict(_DATOS)
    w._generar_pdf()
    import os
    if getattr(w, "_pdf_ruta", None):
        fab.al_limpiar(lambda r=w._pdf_ruta: os.path.exists(r) and os.remove(r))
    n = N.listar_nominas(eid, emp)[0]
    snap = json.loads(n["conceptos"])
    assert "devengos" in snap and "deducciones" in snap
    assert "bccc" in snap and "bccp" in snap and "ss_trabajador" in snap and "ss_empresa" in snap
    assert snap["meta"]["anio"] == 2026             # versión de parámetros usada


# Salario interpretado como MENSUAL (no se divide por nº pagas)
def test_salario_interpretado_mensual():
    res = calcular_desde_datos(dict(salario="2000", num_pagas="14", grupo_cotizacion="1"))
    # base de cotización = 2000 + prorrateo(2000*2/12=333.33) = 2333.33 (no 2000/14)
    assert res.bccc == round(2000 + 333.33, 2)
