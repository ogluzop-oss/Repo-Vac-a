"""
F4.2 · Render dedicado VACACIONES (deja de usar render_generico).

Verifica dispatch, generación de PDF real por subtipo (SOLICITUD/APROBACIÓN/DENEGACIÓN),
contenido específico (fechas, días) y que NO se usa la rama genérica.
"""

import os

import pytest

pytestmark = pytest.mark.db

_SUBTIPOS = ["SOLICITUD", "APROBACIÓN", "DENEGACIÓN"]
_DATOS = dict(trabajador="ANA LOPEZ", nif="00000000T", fecha="01/07/2026",
              fecha_fin_vac="15/07/2026", responsable="El Gerente",
              motivo_baja="necesidades del servicio")


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
    w._tipo = "VACACIONES"
    w._datos = dict(_DATOS, subtipo=subtipo)
    w._generar_pdf()
    return cap.get("sig", [])


def test_dispatch_usa_render_dedicado():
    from src.rrhh.documents import render as R
    import src.gui.gestion_usuarios as gu
    import inspect
    assert callable(R.render_vacaciones)
    src = inspect.getsource(gu._WizardDocumentoFiscal._generar_pdf)
    assert '"VACACIONES": render_vacaciones' in src


@pytest.mark.parametrize("subtipo", _SUBTIPOS)
def test_genera_pdf_real_por_subtipo(subtipo, fab, db):
    _app()
    import src.gui.gestion_usuarios as gu
    w = gu._WizardDocumentoFiscal()
    w._tipo = "VACACIONES"
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


def test_contenido_especifico_y_dias(monkeypatch):
    _app()
    textos = " ".join(getattr(f, "text", "") or "" for f in _flowables("SOLICITUD", monkeypatch))
    assert "vacaciones" in textos and "solicita el disfrute" in textos
    assert "01/07/2026" in textos and "15/07/2026" in textos    # fechas solicitadas
    assert "15 días" in textos                                  # nº de días (1-15 jul = 15)
    # Subtipos producen textos distintos (aprobación vs denegación).
    aprob = " ".join(getattr(f, "text", "") or "" for f in _flowables("APROBACIÓN", monkeypatch))
    deneg = " ".join(getattr(f, "text", "") or "" for f in _flowables("DENEGACIÓN", monkeypatch))
    assert "APRUEBA" in aprob and "DENEGACIÓN" in deneg


def test_no_generico(monkeypatch):
    _app()
    assert len(_flowables("SOLICITUD", monkeypatch)) > 13       # > documento genérico
