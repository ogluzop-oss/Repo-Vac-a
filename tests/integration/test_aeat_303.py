"""
AEAT · FASE 1 — Infraestructura común + Modelo 303 completo (casillas, persistencia,
idempotencia, auditoría, exportación, PDF, multiempresa, estados).
"""

import os

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant
from src.services.aeat import base as B, estados as ST, exportacion as X, modelo_303 as M
from src.services.contabilidad import asientos as A, cuentas as K

E = EMPRESA_DEFAULT_ID
EJ = 2031          # ejercicio aislado para no chocar con otros tests


def _asiento_iva(cuenta_iva, tipo_iva, base_imp, cuota, fecha, repercutido):
    """Crea un asiento cuadrado con una línea de IVA (477 repercutido / 472 soportado)."""
    if repercutido:   # venta: Debe 430 ; Haber 700 + 477
        lineas = [{"codigo_cuenta": "430", "debe": base_imp + cuota, "haber": 0},
                  {"codigo_cuenta": "700", "debe": 0, "haber": base_imp},
                  {"codigo_cuenta": cuenta_iva, "debe": 0, "haber": cuota, "tipo_iva": tipo_iva}]
    else:             # compra: Debe 600 + 472 ; Haber 400
        lineas = [{"codigo_cuenta": "600", "debe": base_imp, "haber": 0},
                  {"codigo_cuenta": cuenta_iva, "debe": cuota, "haber": 0, "tipo_iva": tipo_iva},
                  {"codigo_cuenta": "400", "debe": 0, "haber": base_imp + cuota}]
    return A.crear_asiento(fecha, lineas, concepto="test iva", id_empresa=E)


@pytest.fixture
def libro(db):
    K.activar(E)
    with contexto_tenant(E, None):
        _asiento_iva("477", 21, 1000, 210, f"{EJ}-02-10", True)    # repercutido 21%
        _asiento_iva("477", 10, 500, 50, f"{EJ}-02-15", True)      # repercutido 10%
        _asiento_iva("472", 21, 400, 84, f"{EJ}-03-01", False)     # soportado 21%
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE l FROM contab_apuntes l JOIN contab_asientos a ON a.id=l.id_asiento "
                    "WHERE a.id_empresa=%s AND a.anio=%s", (E, EJ))
        cur.execute("DELETE FROM contab_asientos WHERE id_empresa=%s AND anio=%s", (E, EJ))
        cur.execute("DELETE l FROM aeat_declaracion_lineas l JOIN aeat_declaraciones d "
                    "ON d.id=l.id_declaracion WHERE d.id_empresa=%s AND d.ejercicio=%s", (E, EJ))
        cur.execute("DELETE FROM aeat_declaraciones WHERE id_empresa=%s AND ejercicio=%s", (E, EJ))
        conn.commit()


# ── Cálculo de casillas ───────────────────────────────────────────────────────
def test_casillas_303(libro):
    m = M.Modelo303(EJ, "1T", id_empresa=E)
    cas = {c["casilla"]: c["importe"] for c in m.casillas()}
    assert cas["01"] == 1000.0 and cas["03"] == 210.0      # base/cuota 21% devengado
    assert cas["04"] == 500.0 and cas["06"] == 50.0        # base/cuota 10% devengado
    assert cas["27"] == 260.0                              # cuota devengada total (210+50)
    assert cas["29"] == 84.0                               # IVA deducible
    assert cas["45"] == 84.0
    assert cas["46"] == 176.0                              # 260 - 84
    assert cas["69"] == 176.0 and cas["71"] == 176.0
    assert m.resultado == 176.0 and m.sentido == "a ingresar"


def test_continuidad_con_resumen_303(libro):
    from src.services.contabilidad import iva as IVA
    m = M.Modelo303(EJ, "1T", id_empresa=E)
    base = IVA.resumen_303(E, EJ, f"{EJ}-01-01", f"{EJ}-03-31")
    assert m.resultado == base["resultado"]                # el motor existente no cambia


# ── Persistencia + idempotencia + auditoría ──────────────────────────────────
def test_generar_persiste_e_idempotente(db, libro):
    r1 = M.generar(EJ, "1T", id_empresa=E)
    assert r1["ok"] and r1["resultado"] == 176.0
    d = B.obtener_declaracion(r1["id"], id_empresa=E)
    assert d["estado"] == ST.GENERADO and d["hash"] and len(d["casillas"]) >= 12
    r2 = M.generar(EJ, "1T", id_empresa=E)               # idempotente: misma declaración
    assert r2["id"] == r1["id"]
    assert len(B.listar_declaraciones(modelo="303", ejercicio=EJ, id_empresa=E)) == 1
    # auditoría
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM auditoria_logs WHERE accion='AEAT_303_GENERADO'")
        assert (cur.fetchone()[0] or 0) >= 1


def test_pdf_y_exportacion(libro):
    r = M.generar(EJ, "1T", id_empresa=E)
    assert r["pdf"] and os.path.exists(r["pdf"])
    d = B.obtener_declaracion(r["id"], id_empresa=E)
    js = X.a_json(d); cs = X.a_csv(d)
    assert '"casilla": "27"' in js
    assert cs.splitlines()[0] == "casilla;descripcion;importe" and "27;" in cs


# ── Estados ───────────────────────────────────────────────────────────────────
def test_estados(libro):
    r = M.generar(EJ, "2T", id_empresa=E)
    did = r["id"]
    assert B.cambiar_estado(did, ST.PRESENTADO, id_empresa=E)
    d = B.obtener_declaracion(did, id_empresa=E)
    assert d["estado"] == ST.PRESENTADO and d["fecha_presentacion"]
    # presentada → no se sobreescribe al regenerar
    r2 = M.generar(EJ, "2T", id_empresa=E)
    assert r2["ok"] is False
    # transición ilegal
    with pytest.raises(ValueError):
        B.cambiar_estado(did, ST.BORRADOR, id_empresa=E)


# ── Multiempresa ──────────────────────────────────────────────────────────────
def test_aislamiento_multiempresa(db, libro, fab):
    emp2 = fab.empresa("AEAT B")
    r = M.generar(EJ, "1T", id_empresa=E)
    assert r["ok"]
    # la empresa 2 no ve la declaración de E
    assert all(x["id"] != r["id"] for x in B.listar_declaraciones(modelo="303", id_empresa=emp2))


# ── GUI headless ──────────────────────────────────────────────────────────────
def test_gui_aeat(db, libro):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    with contexto_tenant(E, None):
        from src.gui.aeat_gui import AEATWindow
        w = AEATWindow()
        assert w.tbl_decl is not None and w.tbl_cas is not None
        w.close()
