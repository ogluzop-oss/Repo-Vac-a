"""
F3.0.4b · Extracción del render documental RRHH a servicios (src/rrhh/documents/render).

Verifica que los servicios existen, que el wizard sigue importándose y delegando, que
no hay ciclos de import y que el contexto auto-capturado produce documentos idénticos
(la equivalencia byte-estructural la garantiza el golden de test_rrhh_pdf_decomp.py).
"""

import subprocess
import sys

import pytest

_SERVICIOS = ("render_contrato", "render_nomina", "render_carta_despido", "render_certificado",
              "render_alta_baja", "render_finiquito", "render_generico")


def test_servicios_existen_e_importables():
    from src.rrhh.documents import render as R
    for fn in _SERVICIOS:
        assert callable(getattr(R, fn))


def test_servicios_reciben_ctx():
    import inspect
    from src.rrhh.documents import render as R
    for fn in _SERVICIOS:
        params = list(inspect.signature(getattr(R, fn)).parameters)
        assert params == ["ctx"], f"{fn} firma inesperada: {params}"


def test_wizard_sigue_importando():
    import src.gui.gestion_usuarios as gu
    assert hasattr(gu, "_WizardDocumentoFiscal")
    assert hasattr(gu, "ConfiguracionWindow")


def _impl_demo():   # nivel de módulo → sin freevars, como los _impl reales del render
    salida.append(valor_inyectado + 1)   # noqa: F821 (resueltos desde ctx)


def test_contexto_ejecutar_inyecta_scope():
    """`ejecutar` corre el cuerpo con ctx como espacio de nombres (sin lógica nueva)."""
    from src.rrhh.documents.render.contexto import ejecutar
    salida = []
    ejecutar(_impl_demo, {"valor_inyectado": 41, "salida": salida})
    assert salida == [42]


@pytest.mark.parametrize("orden", [
    "import src.gui.gestion_usuarios; import src.rrhh.documents.render",
    "import src.rrhh.documents.render; import src.gui.gestion_usuarios",
])
def test_sin_ciclos_de_import(orden):
    import os
    r = subprocess.run([sys.executable, "-c", orden + "; print('OK')"],
                       capture_output=True, text=True,
                       env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr
