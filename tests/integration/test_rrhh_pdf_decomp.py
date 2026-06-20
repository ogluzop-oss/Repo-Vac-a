"""
F3.0.4a · Descomposición interna de _generar_pdf en closures (sin cambio funcional).

Test "golden": con datos fijos, captura la secuencia de flowables del PDF (sin
renderizar a disco) por tipo y la compara con la firma congelada en la descomposición.
Garantiza equivalencia estructural exacta antes/después. CERT LABORAL y VACACIONES
deben seguir cayendo en la rama genérica (misma firma).
"""

import hashlib

import pytest

# Firma congelada (n_flowables, hash12) capturada del comportamiento PRE-descomposición.
GOLDEN = {
    "CONTRATO":      (55, "c656267ae3bc"),
    "NÓMINA":        (41, "fb12b461013d"),   # F4.8: recibo oficial de salarios
    "ALTA":          (21, "c2319c1bf6ac"),
    "BAJA":          (21, "49a44900c37e"),
    "CERTIFICADO":   (19, "d01ec62e0fa4"),
    "CERT LABORAL":  (21, "b8ab63bc99bc"),   # F4.2: plantilla dedicada (ya no genérica)
    "CARTA DESPIDO": (31, "5f71cc061819"),
    "FINIQUITO":     (24, "c972cd0dd66f"),
    "VACACIONES":    (22, "e8134faacd65"),   # F4.2: plantilla dedicada (ya no genérica)
}

_DATOS = dict(trabajador="JUAN PEREZ", nif="12345678Z", ss="281234567840",
              fecha="01/06/2026", subtipo="INDEFINIDO", puesto="Mozo", salario="1200",
              num_pagas="14", irpf_pct="15", ss_pct="6.35", convenio="Comercio",
              observaciones="obs test", funciones="varias", grupo_prof="II",
              articulo_et="52", plus_convenio="30", horas_semanales="40")


def _app():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    return QApplication.instance() or QApplication([])


def _firma(tipo, monkeypatch):
    """Genera el documento capturando la secuencia de flowables (sin escribir PDF)."""
    import reportlab.platypus as P
    import src.gui.gestion_usuarios as gu
    cap = {}

    def _fake_build(self, story, *a, **k):
        cap["sig"] = [type(f).__name__ + "|" +
                      (getattr(f, "text", "") if isinstance(getattr(f, "text", None), str) else "")
                      for f in story]
        return None

    monkeypatch.setattr(P.SimpleDocTemplate, "build", _fake_build, raising=True)
    w = gu._WizardDocumentoFiscal()
    w._tipo = tipo
    w._datos = dict(_DATOS)
    w._generar_pdf()
    sig = cap.get("sig", [])
    return len(sig), hashlib.sha256("\n".join(sig).encode()).hexdigest()[:12]


@pytest.mark.parametrize("tipo", list(GOLDEN))
def test_equivalencia_estructural(tipo, monkeypatch):
    _app()
    n, h = _firma(tipo, monkeypatch)
    assert (n, h) == GOLDEN[tipo], f"{tipo}: firma {(n, h)} != golden {GOLDEN[tipo]}"


def test_cert_laboral_y_vacaciones_no_son_genericos(monkeypatch):
    """F4.2: ambos tipos tienen plantilla dedicada → ya NO usan la rama genérica
    (13 flowables / a8aa14e60bca) y producen documentos distintos entre sí."""
    _app()
    GENERICO = (13, "a8aa14e60bca")
    cl = _firma("CERT LABORAL", monkeypatch)
    vac = _firma("VACACIONES", monkeypatch)
    assert cl != GENERICO and vac != GENERICO
    assert cl != vac


def test_dispatch_delega_en_servicios_render():
    """Tras F3.0.4b el render RRHH se delega en servicios src/rrhh/documents/render/*;
    el wizard solo conserva ctx auto-capturado, dispatch y la rama fiscal."""
    import inspect
    import src.gui.gestion_usuarios as gu
    fuente = inspect.getsource(gu._WizardDocumentoFiscal._generar_pdf)
    assert "ctx = {**globals(), **locals()}" in fuente
    assert "_pdf_dispatch.get(self._tipo, render_generico)(ctx)" in fuente
    assert "def _pdf_resumen_fiscal(" in fuente          # fiscal permanece en el wizard
    # Los 7 servicios RRHH existen y son importables.
    from src.rrhh.documents import render as R
    for fn in ("render_contrato", "render_nomina", "render_carta_despido", "render_certificado",
               "render_alta_baja", "render_finiquito", "render_generico"):
        assert callable(getattr(R, fn))
