"""
F4.2 · Render dedicado CERTIFICADO LABORAL (deja de usar render_generico).

Verifica dispatch correcto, generación de PDF real por subtipo, presencia de contenido
específico y que NO se usa la rama genérica.
"""

import os

import pytest

pytestmark = pytest.mark.db

_SUBTIPOS = ["GENERAL", "INGRESOS", "ANTIGÜEDAD", "FUNCIONES", "JORNADA", "VACACIONES"]
_DATOS = dict(trabajador="ANA LOPEZ", nif="00000000T", ss="281111111111", fecha="20/06/2026",
              puesto="Cajera", salario="1300", num_pagas="14", convenio="Comercio",
              funciones="atención al cliente", horas_semanales="40", antiguedad="01/01/2020",
              vacaciones="30")


def _app():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    return QApplication.instance() or QApplication([])


def _flowables(subtipo, monkeypatch):
    import reportlab.platypus as P
    import src.gui.gestion_usuarios as gu
    cap = {}
    monkeypatch.setattr(P.SimpleDocTemplate, "build",
                        lambda self, story, *a, **k: cap.update(sig=list(story)), raising=True)
    w = gu._WizardDocumentoFiscal()
    w._tipo = "CERT LABORAL"
    w._datos = dict(_DATOS, subtipo=subtipo)
    w._generar_pdf()
    return cap.get("sig", [])


def test_dispatch_usa_render_dedicado():
    from src.rrhh.documents import render as R
    import src.gui.gestion_usuarios as gu
    import inspect
    assert callable(R.render_cert_laboral)
    src = inspect.getsource(gu._WizardDocumentoFiscal._generar_pdf)
    assert '"CERT LABORAL": render_cert_laboral' in src


@pytest.mark.parametrize("subtipo", _SUBTIPOS)
def test_genera_pdf_real_por_subtipo(subtipo, fab, db):
    _app()
    import src.gui.gestion_usuarios as gu
    w = gu._WizardDocumentoFiscal()
    w._tipo = "CERT LABORAL"
    w._datos = dict(_DATOS, subtipo=subtipo)
    w._generar_pdf()
    ruta = getattr(w, "_pdf_ruta", None)
    assert ruta and os.path.exists(ruta) and os.path.getsize(ruta) > 1500
    fab.al_limpiar(lambda r=ruta: os.path.exists(r) and os.remove(r))
    with open(ruta, "rb") as f:
        head = f.read(5)
    with open(ruta, "rb") as f:
        tail = f.read()[-8:]
    assert head == b"%PDF-" and b"%%EOF" in tail
    w.close()


def test_contenido_especifico_y_no_generico(monkeypatch):
    _app()
    # Texto del certificado presente (CERTIFICA + cabecera del subtipo).
    textos = " ".join(getattr(f, "text", "") or "" for f in _flowables("INGRESOS", monkeypatch))
    assert "CERTIFICA" in textos                       # párrafo "CERTIFICA:"
    assert "salario bruto mensual" in textos          # cuerpo específico de INGRESOS
    # No es el documento genérico (una sola línea obs/doc_id).
    assert len(_flowables("GENERAL", monkeypatch)) > 13
