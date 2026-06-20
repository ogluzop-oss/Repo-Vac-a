"""
F3.0.4c · Extracción de formularios RRHH a WizardFormsRRHHMixin.

Verifica MRO, herencia de los 10 métodos, construcción real de las páginas RRHH
(página 1 trabajador + página 2 por tipo), creación de campos y ausencia de ciclos.
La equivalencia documental la garantiza el golden de test_rrhh_pdf_decomp.py.
"""

import os
import subprocess
import sys

import pytest

_METODOS = ("_p1_worker", "_p2_CONTRATO", "_p2_NOMINA", "_p2_ALTA", "_p2_BAJA",
            "_p2_CERTIFICADO", "_p2_CERT_LABORAL", "_p2_CARTA_DESPIDO", "_p2_FINIQUITO",
            "_p2_VACACIONES")
_TIPOS = ["CONTRATO", "NÓMINA", "ALTA", "BAJA", "CERTIFICADO", "CERT LABORAL",
          "CARTA DESPIDO", "FINIQUITO", "VACACIONES"]


def _app():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    return QApplication.instance() or QApplication([])


def test_mixin_en_mro():
    import src.gui.gestion_usuarios as gu
    from src.rrhh.documents.forms_rrhh import WizardFormsRRHHMixin
    assert WizardFormsRRHHMixin in gu._WizardDocumentoFiscal.__mro__


def test_metodos_heredados():
    import src.gui.gestion_usuarios as gu
    from src.rrhh.documents.forms_rrhh import WizardFormsRRHHMixin
    for m in _METODOS:
        # están en el mixin y son accesibles desde la clase concreta (herencia)
        assert hasattr(WizardFormsRRHHMixin, m)
        assert hasattr(gu._WizardDocumentoFiscal, m)


@pytest.mark.parametrize("tipo", _TIPOS)
def test_construye_paginas_rrhh(tipo):
    """Construir página 1 (trabajador) y 2 (datos) ejercita los métodos del mixin."""
    _app()
    import src.gui.gestion_usuarios as gu
    w = gu._WizardDocumentoFiscal(tipo_inicial=tipo)
    w._paso = 0
    w._render()                      # _p1_worker
    assert w._card_ly is not None
    w._paso = 1
    w._render()                      # _p2_<TIPO>
    assert w._card_ly is not None
    w.close()


def test_nomina_crea_campos():
    _app()
    import src.gui.gestion_usuarios as gu
    w = gu._WizardDocumentoFiscal(tipo_inicial="NÓMINA")
    w._paso = 1
    w._render()
    for attr in ("_inp_sal", "_inp_irpf", "_inp_ss_pct", "_combo_pagas"):
        assert hasattr(w, attr), f"falta campo {attr}"
    w.close()


@pytest.mark.parametrize("orden", [
    "import src.gui.gestion_usuarios; import src.rrhh.documents.forms_rrhh",
    "import src.rrhh.documents.forms_rrhh; import src.gui.gestion_usuarios",
])
def test_sin_ciclos_de_import(orden):
    r = subprocess.run([sys.executable, "-c", orden + "; print('OK')"],
                       capture_output=True, text=True,
                       env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr
