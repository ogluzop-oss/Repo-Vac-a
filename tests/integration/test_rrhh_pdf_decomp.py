"""
F3.0.4a · Descomposición interna de _generar_pdf en closures (sin cambio funcional).

Test "golden": con datos fijos, captura la secuencia de flowables del PDF (sin
renderizar a disco) por tipo y la compara con la firma congelada en la descomposición.
Garantiza equivalencia estructural exacta antes/después. CERT LABORAL y VACACIONES
deben seguir cayendo en la rama genérica (misma firma).
"""

import hashlib

import pytest

# Firma congelada (n_flowables, hash12). El test fija TODAS sus entradas variables para ser
# DETERMINISTA y PORTABLE (ver `_firma`): (1) la fecha (`_FechaFija`), (2) los datos corporativos
# (`_dc_fijo`) y (3) la divisa (EUR). Antes la firma dependía de la empresa/moneda residentes en la BD
# (no portable) → fallaba fuera del equipo donde se capturó. Regenerar tras un cambio intencionado de
# plantilla: capturar con estas MISMAS entradas fijas y pegar aquí (n, hash).
GOLDEN = {
    "CONTRATO":      (58, "1f41a22f5504"),
    "NÓMINA":        (41, "824ce33930e8"),   # F4.8: recibo oficial de salarios
    "ALTA":          (21, "9b0cab304bcc"),
    "BAJA":          (21, "afe4eeedc295"),
    "CERTIFICADO":   (19, "1d196be15fdd"),
    "CERT LABORAL":  (21, "ff008823f4a0"),   # F4.2: plantilla dedicada (ya no genérica)
    "CARTA DESPIDO": (31, "b723520e0c8f"),
    "FINIQUITO":     (24, "2b11f3a5f0ff"),
    "VACACIONES":    (22, "5fcf69e44010"),   # F4.2: plantilla dedicada (ya no genérica)
}

_DATOS = dict(trabajador="JUAN PEREZ", nif="12345678Z", ss="281234567840",
              fecha="01/06/2026", subtipo="INDEFINIDO", puesto="Mozo", salario="1200",
              num_pagas="14", irpf_pct="15", ss_pct="6.35", convenio="Comercio",
              observaciones="obs test", funciones="varias", grupo_prof="II",
              articulo_et="52", plus_convenio="30", horas_semanales="40")

# Datos corporativos FIJOS (empresa/representante/centro) para que la firma NO dependa de la empresa
# que haya en la BD. Cubren todos los campos que lee `_generar_pdf` (los ausentes caen a "" de forma
# determinista igualmente).
_EMPRESA_FIJA = {
    "razon_social": "EMPRESA DEMO S.L.", "nombre_empresa": "EMPRESA DEMO S.L.",
    "nombre_comercial": "Demo", "cif_nif": "B00000000", "direccion_fiscal": "Calle Falsa 123",
    "telefono": "900000000", "email_principal": "info@demo.example", "ccc": "28/0000000/00",
    "municipio": "Madrid", "cod_municipio": "28079", "cp": "28001", "provincia": "Madrid",
    "cod_provincia": "28", "pais": "ESPAÑA", "cod_pais": "ES", "regimen_ss": "0111",
    "cnae": "4711", "cod_actividad": "4711", "actividad_economica": "Comercio al por menor",
    "convenio_colectivo": "Comercio",
}
_REP_FIJO = {"nombre": "ANA", "apellidos": "GARCIA LOPEZ", "dni_nie": "00000000T", "cargo": "Administradora"}
_CENTRO_FIJO = {
    "nombre_centro": "Centro Demo", "codigo_centro_trabajo": "0001",
    "codigo_cuenta_cotizacion": "28/0000000/00", "direccion": "Calle Falsa 123",
    "municipio": "Madrid", "cod_municipio": "28079", "codigo_postal": "28001",
    "provincia": "Madrid", "pais": "ESPAÑA", "cod_pais": "ES",
    "actividad_economica": "Comercio al por menor", "cod_actividad": "4711",
}


def _dc_fijo(*a, **k):
    return {"empresa": dict(_EMPRESA_FIJA), "representante": dict(_REP_FIJO), "centro": dict(_CENTRO_FIJO)}


def _app():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    return QApplication.instance() or QApplication([])


import datetime as _dt_mod


class _FechaFija(_dt_mod.datetime):
    """datetime con now() fijo → los golden son estables aunque cambie el día
    (algunos documentos embeben la fecha de hoy en su texto)."""
    @classmethod
    def now(cls, tz=None):
        return _dt_mod.datetime(2026, 6, 20, 12, 0, 0)


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
    monkeypatch.setattr("src.gui.gestion_usuarios.datetime", _FechaFija, raising=True)
    # Empresa/representante/centro FIJOS → firma independiente de la BD (determinista y portable).
    monkeypatch.setattr("src.db.empresa.datos_corporativos", _dc_fijo, raising=True)
    # Divisa FIJA (EUR) → el importe del salario (CONTRATO) no depende de la moneda activa en BD/caché.
    monkeypatch.setattr("src.utils.divisas.divisa_actual", lambda: "EUR", raising=True)
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
