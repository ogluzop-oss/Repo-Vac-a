"""
AEAT · FASE 4 — Modelo 190 (resumen anual de retenciones): perceptores trabajo/profesional,
agregados, persistencia, auditoría, PDF, exportación, multiempresa, regresión 190 == Σ 111.
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import compras
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant
from src.services.aeat import base as B, estados as ST, exportacion as X
from src.services.aeat import modelo_111 as M111, modelo_190 as M190
from src.services.contabilidad import cuentas as K
from src.services.contabilidad.posting import procesar_cola

E = EMPRESA_DEFAULT_ID
EJ = 2035


def _empleado(db, nombre, nif):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO rrhh_empleados (id_empresa, id_tienda, nombre, nif) "
                    "VALUES (%s,'',%s,%s)", (E, nombre, nif))
        eid = cur.lastrowid; conn.commit()
    return eid


def _nomina(db, id_emp, mes, bruto, irpf):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO rrhh_nominas (id_empresa, id_empleado, anio, mes, bruto, base, "
                    "irpf_importe) VALUES (%s,%s,%s,%s,%s,%s,%s)", (E, id_emp, EJ, mes, bruto, bruto, irpf))
        conn.commit()


def _proveedor(db, razon, cif):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO proveedores (id_empresa, razon_social, cif_nif) VALUES (%s,%s,%s)",
                    (E, razon, cif))
        pid = cur.lastrowid; conn.commit()
    return pid


@pytest.fixture
def datos(db):
    K.activar(E)
    e1 = _empleado(db, "Ana", "11111111H")
    e2 = _empleado(db, "Luis", "22222222J")
    _nomina(db, e1, 2, 2000, 300); _nomina(db, e1, 5, 2000, 300)     # Ana: 600 (Q1+Q2)
    _nomina(db, e2, 8, 1000, 100)                                     # Luis: 100 (Q3)
    p1 = _proveedor(db, "Gestoría SL", "B11111111")
    p2 = _proveedor(db, "Abogado", "33333333P")
    empleados = [e1, e2]; provs = [p1, p2]
    with contexto_tenant(E, None):
        compras.registrar_factura(id_proveedor=p1, numero_factura="A1", base=1000, iva=210,
                                  retencion_pct=15, fecha_factura=f"{EJ}-03-10", id_empresa=E)   # ret 150
        compras.registrar_factura(id_proveedor=p2, numero_factura="A2", base=2000, iva=420,
                                  retencion_pct=15, fecha_factura=f"{EJ}-11-10", id_empresa=E)   # ret 300
        procesar_cola(E)
    yield {"empleados": empleados, "provs": provs}
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE l FROM contab_apuntes l JOIN contab_asientos a ON a.id=l.id_asiento "
                    "WHERE a.id_empresa=%s AND a.anio=%s", (E, EJ))
        cur.execute("DELETE FROM contab_asientos WHERE id_empresa=%s AND anio=%s", (E, EJ))
        cur.execute("DELETE FROM contab_cola WHERE id_empresa=%s AND evento='compra'", (E,))
        cur.execute("DELETE FROM compras_facturas WHERE id_empresa=%s AND fecha_factura LIKE %s", (E, f"{EJ}-%"))
        cur.execute("DELETE FROM proveedores WHERE id_proveedor IN (%s,%s)", (p1, p2))
        cur.execute("DELETE FROM rrhh_nominas WHERE id_empresa=%s AND anio=%s", (E, EJ))
        cur.execute("DELETE FROM rrhh_empleados WHERE id IN (%s,%s)", (e1, e2))
        cur.execute("DELETE l FROM aeat_declaracion_lineas l JOIN aeat_declaraciones d "
                    "ON d.id=l.id_declaracion WHERE d.id_empresa=%s AND d.ejercicio=%s", (E, EJ))
        cur.execute("DELETE FROM aeat_declaraciones WHERE id_empresa=%s AND ejercicio=%s", (E, EJ))
        conn.commit()


# ── Perceptores ───────────────────────────────────────────────────────────────
def test_perceptores_trabajo_y_profesional(datos):
    m = M190.Modelo190(EJ, id_empresa=E)
    trab = [p for p in m.perceptores if p.clave == "TRABAJO"]
    prof = [p for p in m.perceptores if p.clave == "PROFESIONAL"]
    assert len(trab) == 2 and len(prof) == 2
    ana = next(p for p in trab if p.nif == "11111111H")
    assert ana.retenciones == 600.0 and ana.percepciones == 4000.0
    gestoria = next(p for p in prof if p.nif == "B11111111")
    assert gestoria.retenciones == 150.0 and gestoria.percepciones == 1000.0


def test_casillas_agregadas(datos):
    m = M190.Modelo190(EJ, id_empresa=E)
    cas = {c["casilla"]: c["importe"] for c in m.casillas() if c["casilla"] in
           ("01", "02", "03", "T_RET", "P_RET", "T_NUM", "P_NUM")}
    assert cas["01"] == 4              # 2 trabajadores + 2 profesionales
    assert cas["T_RET"] == 700.0       # 600 + 100
    assert cas["P_RET"] == 450.0       # 150 + 300
    assert cas["03"] == 1150.0         # total retenciones
    assert m.resultado == 1150.0


# ── Regresión obligatoria: 190 anual == suma de los 111 del ejercicio ────────
def test_190_igual_suma_111(datos):
    m = M190.Modelo190(EJ, id_empresa=E)
    suma_111 = round(sum(M111.Modelo111(EJ, q, id_empresa=E).resultado
                         for q in ("1T", "2T", "3T", "4T")), 2)
    assert m.resultado == suma_111 == 1150.0


# ── Persistencia + auditoría + idempotencia ──────────────────────────────────
def test_190_persiste_audita_idempotente(db, datos):
    r1 = M190.generar(EJ, id_empresa=E)
    assert r1["ok"] and r1["resultado"] == 1150.0 and len(r1["perceptores"]) == 4
    d = B.obtener_declaracion(r1["id"], id_empresa=E)
    assert d["modelo"] == "190" and d["periodo"] == "0A" and d["estado"] == ST.GENERADO and d["hash"]
    r2 = M190.generar(EJ, id_empresa=E)
    assert r2["id"] == r1["id"]
    assert len(B.listar_declaraciones(modelo="190", ejercicio=EJ, id_empresa=E)) == 1
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM auditoria_logs WHERE accion='AEAT_190_GENERADO'")
        assert (cur.fetchone()[0] or 0) >= 1


def test_190_pdf_export(datos):
    r = M190.generar(EJ, id_empresa=E)
    assert r["pdf"] and os.path.exists(r["pdf"])
    d = B.obtener_declaracion(r["id"], id_empresa=E)
    js = X.a_json(d); cs = X.a_csv(d)
    assert '"modelo": "190"' in js
    assert "11111111H" in cs and "T_PERC" in cs        # perceptores en el detalle


def test_190_multiempresa(db, datos, fab):
    emp2 = fab.empresa("190 B")
    m2 = M190.Modelo190(EJ, id_empresa=emp2)
    assert m2.resultado == 0.0 and m2.perceptores == []
