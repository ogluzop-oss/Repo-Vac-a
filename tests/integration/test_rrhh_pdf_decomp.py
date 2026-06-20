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
    "NÓMINA":        (25, "e275abd79dca"),
    "ALTA":          (21, "c2319c1bf6ac"),
    "BAJA":          (21, "49a44900c37e"),
    "CERTIFICADO":   (19, "d01ec62e0fa4"),
    "CERT LABORAL":  (13, "a8aa14e60bca"),
    "CARTA DESPIDO": (31, "5f71cc061819"),
    "FINIQUITO":     (24, "c972cd0dd66f"),
    "VACACIONES":    (13, "a8aa14e60bca"),
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


def test_cert_laboral_y_vacaciones_usan_generico(monkeypatch):
    """Ambos tipos sin rama propia deben producir la MISMA salida (rama genérica)."""
    _app()
    assert _firma("CERT LABORAL", monkeypatch) == _firma("VACACIONES", monkeypatch)


def test_dispatch_existe_y_cubre_tipos():
    """El método contiene las closures y el dispatch (descomposición aplicada)."""
    import inspect
    import src.gui.gestion_usuarios as gu
    fuente = inspect.getsource(gu._WizardDocumentoFiscal._generar_pdf)
    for closure in ("_pdf_contrato", "_pdf_nomina", "_pdf_alta_baja", "_pdf_certificado",
                    "_pdf_carta_despido", "_pdf_finiquito", "_pdf_resumen_fiscal", "_pdf_generico"):
        assert f"def {closure}(" in fuente, f"falta closure {closure}"
    assert "_pdf_dispatch" in fuente and "_pdf_dispatch.get(self._tipo, _pdf_generico)" in fuente
