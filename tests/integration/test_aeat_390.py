"""
AEAT · FASE 2 — Modelo 390 (resumen anual IVA): agregación, consistencia con 303,
persistencia, auditoría, PDF, exportación, multiempresa.
"""

import os

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant
from src.services.aeat import base as B, estados as ST, exportacion as X
from src.services.aeat import modelo_303 as M303, modelo_390 as M390
from src.services.contabilidad import asientos as A, cuentas as K

E = EMPRESA_DEFAULT_ID
EJ = 2032


def _asiento(cuenta, tipo, base, cuota, fecha, rep):
    if rep:
        lineas = [{"codigo_cuenta": "430", "debe": base + cuota, "haber": 0},
                  {"codigo_cuenta": "700", "debe": 0, "haber": base},
                  {"codigo_cuenta": cuenta, "debe": 0, "haber": cuota, "tipo_iva": tipo}]
    else:
        lineas = [{"codigo_cuenta": "600", "debe": base, "haber": 0},
                  {"codigo_cuenta": cuenta, "debe": cuota, "haber": 0, "tipo_iva": tipo},
                  {"codigo_cuenta": "400", "debe": 0, "haber": base + cuota}]
    return A.crear_asiento(fecha, lineas, concepto="iva test", id_empresa=E)


@pytest.fixture
def ejercicio(db):
    K.activar(E)
    with contexto_tenant(E, None):
        _asiento("477", 21, 1000, 210, f"{EJ}-02-10", True)    # Q1 repercutido
        _asiento("472", 21, 400, 84, f"{EJ}-03-05", False)     # Q1 soportado
        _asiento("477", 10, 500, 50, f"{EJ}-05-10", True)      # Q2 repercutido
        _asiento("477", 21, 2000, 420, f"{EJ}-10-01", True)    # Q4 repercutido
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE l FROM contab_apuntes l JOIN contab_asientos a ON a.id=l.id_asiento "
                    "WHERE a.id_empresa=%s AND a.anio=%s", (E, EJ))
        cur.execute("DELETE FROM contab_asientos WHERE id_empresa=%s AND anio=%s", (E, EJ))
        cur.execute("DELETE l FROM aeat_declaracion_lineas l JOIN aeat_declaraciones d "
                    "ON d.id=l.id_declaracion WHERE d.id_empresa=%s AND d.ejercicio=%s", (E, EJ))
        cur.execute("DELETE FROM aeat_declaraciones WHERE id_empresa=%s AND ejercicio=%s", (E, EJ))
        conn.commit()


def _suma_trimestres_71():
    total = 0.0
    for q in ("1T", "2T", "3T", "4T"):
        total += M303.Modelo303(EJ, q, id_empresa=E).resultado
    return round(total, 2)


# ── Agregación anual = suma de los 303 ───────────────────────────────────────
def test_390_consolida_trimestres(ejercicio):
    m = M390.Modelo390(EJ, id_empresa=E)
    cas = {c["casilla"]: c["importe"] for c in m.casillas()}
    # devengado: 21% = 210(Q1)+420(Q4)=630 ; 10% = 50 ; total 27 = 680
    assert cas["03"] == 630.0 and cas["06"] == 50.0
    assert cas["27"] == 680.0
    assert cas["29"] == 84.0 and cas["45"] == 84.0       # deducible anual
    assert cas["46"] == 596.0 and cas["71"] == 596.0     # 680 - 84
    assert m.resultado == 596.0


def test_390_igual_suma_303(ejercicio):
    """Regresión: el 390 debe coincidir con la suma de los 303 del ejercicio."""
    m = M390.Modelo390(EJ, id_empresa=E)
    assert m.resultado == _suma_trimestres_71()
    # y también con el cálculo anual directo (0A)
    assert m.resultado == M303.Modelo303(EJ, "0A", id_empresa=E).resultado


# ── Persistencia + auditoría + idempotencia ──────────────────────────────────
def test_390_persiste_audita_idempotente(db, ejercicio):
    r1 = M390.generar(EJ, id_empresa=E)
    assert r1["ok"] and r1["resultado"] == 596.0 and r1["trimestres"] == ["1T", "2T", "3T", "4T"]
    d = B.obtener_declaracion(r1["id"], id_empresa=E)
    assert d["modelo"] == "390" and d["periodo"] == "0A" and d["estado"] == ST.GENERADO and d["hash"]
    r2 = M390.generar(EJ, id_empresa=E)
    assert r2["id"] == r1["id"]                            # idempotente
    decls = [x for x in B.listar_declaraciones(modelo="390", ejercicio=EJ, id_empresa=E)]
    assert len(decls) == 1
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM auditoria_logs WHERE accion='AEAT_390_GENERADO'")
        assert (cur.fetchone()[0] or 0) >= 1


def test_390_pdf_export(ejercicio):
    r = M390.generar(EJ, id_empresa=E)
    assert r["pdf"] and os.path.exists(r["pdf"])
    d = B.obtener_declaracion(r["id"], id_empresa=E)
    assert '"modelo": "390"' in X.a_json(d)
    assert X.a_csv(d).splitlines()[0] == "casilla;descripcion;importe"


def test_390_no_sobreescribe_presentada(ejercicio):
    r = M390.generar(EJ, id_empresa=E)
    assert B.cambiar_estado(r["id"], ST.PRESENTADO, id_empresa=E)
    r2 = M390.generar(EJ, id_empresa=E)
    assert r2["ok"] is False


def test_390_multiempresa(db, ejercicio, fab):
    emp2 = fab.empresa("390 B")
    r = M390.generar(EJ, id_empresa=E)
    assert all(x["id"] != r["id"] for x in B.listar_declaraciones(modelo="390", id_empresa=emp2))
