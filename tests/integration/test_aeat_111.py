"""
AEAT · FASE 3 — Retenciones + Modelo 111: captura profesional, asiento 4751, consolidación
trabajo+profesionales, persistencia, auditoría, PDF, exportación, multiempresa, regresiones.
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import compras
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant
from src.services.aeat import base as B, estados as ST, exportacion as X, modelo_111 as M111
from src.services.contabilidad import cuentas as K
from src.services.contabilidad.posting import procesar_cola

E = EMPRESA_DEFAULT_ID
EJ = 2034


def _empleado(db, nif):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO rrhh_empleados (id_empresa, id_tienda, nombre, nif) "
                    "VALUES (%s,'',%s,%s)", (E, "Trabajador", nif))
        eid = cur.lastrowid
        conn.commit()
    return eid


def _nomina(db, id_emp, mes, bruto, irpf):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO rrhh_nominas (id_empresa, id_empleado, anio, mes, bruto, base, "
                    "irpf_importe) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (E, id_emp, EJ, mes, bruto, bruto, irpf))
        conn.commit()


@pytest.fixture
def datos(db):
    K.activar(E)
    emp = _empleado(db, "111" + uuid.uuid4().hex[:6])
    _nomina(db, emp, 2, 2000, 300)        # Q1 nómina: IRPF 300
    _nomina(db, emp, 3, 2000, 200)        # Q1 nómina: IRPF 200
    fids = []
    with contexto_tenant(E, None):
        fids.append(compras.registrar_factura(id_proveedor=7, numero_factura="P1", base=1000,
                    iva=210, retencion_pct=15, fecha_factura=f"{EJ}-02-10", id_empresa=E))   # ret 150
        fids.append(compras.registrar_factura(id_proveedor=8, numero_factura="P2", base=400,
                    iva=84, retencion_importe=60, fecha_factura=f"{EJ}-03-01", id_empresa=E))  # ret 60
        fids.append(compras.registrar_factura(id_proveedor=9, numero_factura="P3", base=500,
                    iva=105, fecha_factura=f"{EJ}-03-15", id_empresa=E))                       # SIN retención
        procesar_cola(E)
    yield {"emp": emp, "fids": fids}
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE l FROM contab_apuntes l JOIN contab_asientos a ON a.id=l.id_asiento "
                    "WHERE a.id_empresa=%s AND a.anio=%s", (E, EJ))
        cur.execute("DELETE FROM contab_asientos WHERE id_empresa=%s AND anio=%s", (E, EJ))
        cur.execute("DELETE FROM contab_cola WHERE id_empresa=%s AND evento='compra'", (E,))
        cur.execute("DELETE FROM compras_facturas WHERE id_empresa=%s AND fecha_factura LIKE %s",
                    (E, f"{EJ}-%"))
        cur.execute("DELETE FROM rrhh_nominas WHERE id_empresa=%s AND anio=%s", (E, EJ))
        cur.execute("DELETE l FROM aeat_declaracion_lineas l JOIN aeat_declaraciones d "
                    "ON d.id=l.id_declaracion WHERE d.id_empresa=%s AND d.ejercicio=%s", (E, EJ))
        cur.execute("DELETE FROM aeat_declaraciones WHERE id_empresa=%s AND ejercicio=%s", (E, EJ))
        cur.execute("DELETE FROM rrhh_empleados WHERE id=%s", (emp,))
        conn.commit()


# ── Retención profesional capturada ──────────────────────────────────────────
def test_retencion_capturada_y_compat(db, datos):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT total, retencion_importe FROM compras_facturas WHERE id_factura=%s",
                    (datos["fids"][0],))
        total, ret = cur.fetchone()
        assert float(ret) == 150.0 and float(total) == 1060.0       # 1000+210-150
        # factura SIN retención: total = base+iva, retención 0 (compatibilidad)
        cur.execute("SELECT total, retencion_importe FROM compras_facturas WHERE id_factura=%s",
                    (datos["fids"][2],))
        total3, ret3 = cur.fetchone()
        assert float(ret3) == 0.0 and float(total3) == 605.0


# ── Asiento contable 4751 ─────────────────────────────────────────────────────
def test_asiento_4751(db, datos):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT ap.haber FROM contab_apuntes ap JOIN contab_asientos a ON a.id=ap.id_asiento "
                    "WHERE a.ref_origen=%s AND ap.codigo_cuenta='4751'", (f"compra:{datos['fids'][0]}",))
        r = cur.fetchone()
        assert r and float(r[0]) == 150.0
        # factura sin retención NO genera línea 4751
        cur.execute("SELECT COUNT(*) FROM contab_apuntes ap JOIN contab_asientos a ON a.id=ap.id_asiento "
                    "WHERE a.ref_origen=%s AND ap.codigo_cuenta='4751'", (f"compra:{datos['fids'][2]}",))
        assert cur.fetchone()[0] == 0


# ── Modelo 111: consolidación trabajo + profesionales ────────────────────────
def test_111_casillas(datos):
    m = M111.Modelo111(EJ, "1T", id_empresa=E)
    cas = {c["casilla"]: c["importe"] for c in m.casillas()}
    assert cas["03"] == 500.0          # retenciones trabajo (300+200)
    assert cas["06"] == 210.0          # retenciones profesionales (150+60)
    assert cas["28"] == 710.0 and cas["30"] == 710.0
    assert m.resultado == 710.0


def test_111_persiste_audita_idempotente(db, datos):
    r1 = M111.generar(EJ, "1T", id_empresa=E)
    assert r1["ok"] and r1["resultado"] == 710.0
    d = B.obtener_declaracion(r1["id"], id_empresa=E)
    assert d["modelo"] == "111" and d["estado"] == ST.GENERADO and d["hash"]
    r2 = M111.generar(EJ, "1T", id_empresa=E)
    assert r2["id"] == r1["id"]
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM auditoria_logs WHERE accion='AEAT_111_GENERADO'")
        assert (cur.fetchone()[0] or 0) >= 1


def test_111_pdf_export(datos):
    r = M111.generar(EJ, "1T", id_empresa=E)
    assert r["pdf"] and os.path.exists(r["pdf"])
    d = B.obtener_declaracion(r["id"], id_empresa=E)
    assert '"modelo": "111"' in X.a_json(d)
    assert "28;" in X.a_csv(d)


# ── Regresiones ───────────────────────────────────────────────────────────────
def test_111_periodo_sin_retencion(db, datos):
    # 2T no tiene ni nóminas ni facturas con retención → todo 0
    m = M111.Modelo111(EJ, "2T", id_empresa=E)
    assert m.resultado == 0.0


def test_111_multiempresa(db, datos, fab):
    emp2 = fab.empresa("111 B")
    m2 = M111.Modelo111(EJ, "1T", id_empresa=emp2)
    assert m2.resultado == 0.0          # empresa 2 no ve datos de E
