"""
F4.8 · Recibo oficial de salarios (render de nómina).

Verifica los bloques del recibo (encabezado, devengos, deducciones por contingencia,
aportación empresa, líquido, recibí), que el render NO recalcula (consume el motor),
la coherencia con el motor y la compatibilidad con el expediente.
"""

import inspect
import os
import sys

import pytest

pytestmark = pytest.mark.db

_DATOS = dict(trabajador="Ana Ruiz", nif="80000000A", ss="281234567840", fecha="30/06/2026",
              salario="2000", num_pagas="14", irpf_pct="15", plus_convenio="50",
              nocturnidad="30", plus_transporte="60", dietas="350", anticipos="20",
              grupo_cotizacion="1", puesto="Cajera", grupo_prof="II", convenio="Comercio")


def _app():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    return QApplication.instance() or QApplication([])


def _flat(flow):
    """Texto de un flowable incluyendo celdas de tablas anidadas (recursivo)."""
    out = []
    if isinstance(flow, str):
        out.append(flow); return out
    txt = getattr(flow, "text", None)
    if isinstance(txt, str):
        out.append(txt)
    for row in (getattr(flow, "_cellvalues", None) or []):
        for cell in row:
            out.extend(_flat(cell))
    return out


def _textos(monkeypatch, datos=None):
    import reportlab.platypus as P
    import src.gui.gestion_usuarios as gu
    cap = {}
    monkeypatch.setattr(P.SimpleDocTemplate, "build",
                        lambda self, story, *a, **k: cap.update(s=list(story)), raising=True)
    w = gu._WizardDocumentoFiscal(); w._tipo = "NÓMINA"; w._datos = dict(datos or _DATOS)
    w._generar_pdf()
    partes = []
    for f in cap.get("s", []):
        partes.extend(_flat(f))
    return " ".join(partes)


def test_bloques_del_recibo(monkeypatch):
    _app()
    t = _textos(monkeypatch)
    assert "DEVENGOS SALARIALES" in t                      # bloque devengos salariales
    assert "DEVENGOS NO SALARIALES" in t                   # no salariales (transporte/dietas)
    assert "APORTACIONES DEL TRABAJADOR" in t              # deducciones SS
    assert "Contingencias comunes" in t and "Desempleo" in t and "MEI" in t
    assert "APORTACIÓN DE LA EMPRESA" in t                 # bloque empresa informativo
    assert "LÍQUIDO TOTAL A PERCIBIR" in t                 # resumen destacado
    assert "Recibí" in t                                   # zona de firma


def test_devengos_y_deducciones_detallados(monkeypatch):
    _app()
    t = _textos(monkeypatch)
    assert "Salario base" in t and "Plus convenio" in t and "Nocturnidad" in t
    assert "Plus transporte" in t and "Dietas" in t        # no salariales
    assert "Anticipos" in t                                 # otras deducciones


def test_pdf_real_valido(db, fab):
    _app()
    import src.gui.gestion_usuarios as gu
    w = gu._WizardDocumentoFiscal(); w._tipo = "NÓMINA"; w._datos = dict(_DATOS)
    w._generar_pdf()
    ruta = getattr(w, "_pdf_ruta", None)
    assert ruta and os.path.exists(ruta) and os.path.getsize(ruta) > 2000
    fab.al_limpiar(lambda r=ruta: os.path.exists(r) and os.remove(r))
    with open(ruta, "rb") as f:
        head = f.read(5)
    with open(ruta, "rb") as f:
        tail = f.read()[-8:]
    assert head == b"%PDF-" and b"%%EOF" in tail
    w.close()


def test_render_no_recalcula():
    import src.rrhh.documents.render.render_nomina  # noqa: F401
    mod = sys.modules["src.rrhh.documents.render.render_nomina"]
    src = inspect.getsource(mod)
    assert "calcular_desde_datos" in src
    for prohibido in ("irpf_ret", "ss_ret", "* irpf_pct", "base * ss_pct", "bruto - irpf",
                      "salario / num_pagas"):
        assert prohibido not in src


def test_liquido_coincide_motor(monkeypatch):
    _app()
    from src.rrhh.nomina_servicio import calcular_desde_datos
    res = calcular_desde_datos(_DATOS)
    t = _textos(monkeypatch)
    # el importe del líquido del motor aparece formateado en el recibo
    from src.utils import divisas
    assert divisas.formatear(res.liquido) in t


def test_compatibilidad_expediente(db, fab):
    """Generar la nómina (recibo) para un empleado existente la registra en el expediente."""
    _app()
    from src.db import empresa as empmod
    from src.rrhh.db import empleados as E, nominas as N
    emp = fab.empresa("F48")
    fab.al_limpiar(lambda: _borra(db, emp))
    ctx = empmod.contexto_tenant(emp, None); ctx.__enter__()
    fab.al_limpiar(lambda: ctx.__exit__(None, None, None))
    eid = E.crear_empleado(id_empresa=emp, nombre="Ana", nif="80000000A")
    import src.gui.gestion_usuarios as gu
    w = gu._WizardDocumentoFiscal(); w._tipo = "NÓMINA"; w._datos = dict(_DATOS)
    w._generar_pdf()
    if getattr(w, "_pdf_ruta", None):
        fab.al_limpiar(lambda r=w._pdf_ruta: os.path.exists(r) and os.remove(r))
    assert len(N.listar_nominas(eid, emp)) == 1


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rrhh_empleados WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()
