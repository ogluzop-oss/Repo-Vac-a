"""R1 · Asistente de primeros pasos (OnboardingWizard): cableado a los motores existentes.

- Cableado (con motores mockeados): crea cliente + factura, elige emitir/borrador, genera PDF.
- Real (BD): crea de verdad un cliente y una factura reutilizando `clientes`/`facturas_cliente`
  y exporta su PDF. La GUI solo orquesta; no hay lógica de facturación paralela.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ── Cableado (motores mockeados; sin BD) ──────────────────────────────────────
def test_wizard_cablea_los_motores(app, monkeypatch):
    from src.gui.onboarding_wizard import OnboardingWizard
    import src.db.clientes as CLI
    import src.db.facturas_cliente as FC
    from src.services.facturacion import distribucion as DIST

    monkeypatch.setattr(CLI, "crear_cliente", lambda nombre, **k: 77)
    creada = {}
    monkeypatch.setattr(FC, "crear_factura", lambda **k: creada.update(k) or 501)
    emit = {"n": 0}
    monkeypatch.setattr(FC, "emitir", lambda fid, **k: emit.__setitem__("n", emit["n"] + 1) or True)
    monkeypatch.setattr(DIST, "exportar_factura", lambda fid, **k: "/tmp/factura.pdf")

    w = OnboardingWizard(id_empresa="E1")
    ok, _ = w.crear_cliente("Ana Cliente", nif="12345678A", email="ana@ej.com")
    assert ok and w._cliente_id == 77

    # Borrador de práctica → NO emite.
    ok, _ = w.crear_factura("Servicio de consultoría", 1, 121.0, emitir_real=False)
    assert ok and w._factura_id == 501 and emit["n"] == 0
    assert creada.get("id_cliente") == 77 and creada.get("tipo_documento") == "factura"
    assert creada["lineas"][0]["descripcion"] == "Servicio de consultoría"

    # Real → sí emite.
    ok, _ = w.crear_factura("Otro servicio", 1, 50.0, emitir_real=True)
    assert ok and emit["n"] == 1


# ── Real end-to-end (BD): cliente + factura + PDF ─────────────────────────────
@pytest.mark.db
def test_wizard_crea_cliente_factura_y_pdf_reales(app, db, fab):
    from src.gui.onboarding_wizard import OnboardingWizard

    emp = fab.empresa("ONBOARDING R1")

    def _limpia():
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM facturas_cliente_lineas WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM facturas_cliente WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM clientes WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
            c.commit()
    fab.al_limpiar(_limpia)

    w = OnboardingWizard(id_empresa=emp)
    ok, msg = w.crear_cliente("Cliente Onboarding", nif="12345678A", email="cli@ej.com")
    assert ok and w._cliente_id, msg

    ok, msg = w.crear_factura("Servicio de prueba", 1, 121.0, emitir_real=False)
    assert ok and w._factura_id, msg

    # PDF reproducible desde el snapshot (si reportlab está disponible).
    if w._pdf:
        assert os.path.exists(w._pdf)
        fab.al_limpiar(lambda: os.path.exists(w._pdf) and os.remove(w._pdf))
