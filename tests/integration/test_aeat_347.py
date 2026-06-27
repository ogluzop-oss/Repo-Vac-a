"""
AEAT · FASE 5 — Modelo 347 (operaciones con terceras personas): umbral 3.005,06 €,
desglose trimestral, terceros clientes/proveedores, persistencia, auditoría, export, multiempresa.
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID
from src.services.aeat import base as B, estados as ST, exportacion as X, modelo_347 as M347

E = EMPRESA_DEFAULT_ID
EJ = 2036


def _cliente(db, nombre, nif):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO clientes (nombre, nif, id_empresa) VALUES (%s,%s,%s)", (nombre, nif, E))
        cid = cur.lastrowid; conn.commit()
    return cid


def _proveedor(db, razon, cif):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO proveedores (id_empresa, razon_social, cif_nif) VALUES (%s,%s,%s)",
                    (E, razon, cif))
        pid = cur.lastrowid; conn.commit()
    return pid


def _factura_cliente(db, id_cli, total, fecha):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO facturas_cliente (id_empresa, id_cliente, estado, base, iva, total, "
                    "fecha_emision) VALUES (%s,%s,'emitida',%s,0,%s,%s)",
                    (E, id_cli, total, total, fecha))
        conn.commit()


def _factura_compra(db, id_prov, base, iva, fecha):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO compras_facturas (id_empresa, id_proveedor, numero_factura, "
                    "fecha_factura, base, iva, total, estado) VALUES (%s,%s,%s,%s,%s,%s,%s,'registrada')",
                    (E, id_prov, "C" + uuid.uuid4().hex[:6], fecha, base, iva, base + iva))
        conn.commit()


@pytest.fixture
def datos(db):
    # Cliente sobre umbral repartido en trimestres (2000+1500=3500 > 3005,06)
    c_alto = _cliente(db, "Cliente Grande", "C1111111X")
    _factura_cliente(db, c_alto, 2000, f"{EJ}-02-10")   # T1
    _factura_cliente(db, c_alto, 1500, f"{EJ}-08-10")   # T3
    # Cliente por debajo del umbral (1000) → excluido
    c_bajo = _cliente(db, "Cliente Pequeño", "C2222222Y")
    _factura_cliente(db, c_bajo, 1000, f"{EJ}-03-01")
    # Proveedor sobre umbral (base+iva = 4000+840 = 4840 > umbral)
    p_alto = _proveedor(db, "Proveedor Grande", "B33333333")
    _factura_compra(db, p_alto, 4000, 840, f"{EJ}-11-05")   # T4
    yield {"c_alto": c_alto, "c_bajo": c_bajo, "p_alto": p_alto}
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM facturas_cliente WHERE id_empresa=%s AND id_cliente IN (%s,%s)",
                    (E, c_alto, c_bajo))
        cur.execute("DELETE FROM compras_facturas WHERE id_empresa=%s AND id_proveedor=%s", (E, p_alto))
        cur.execute("DELETE FROM clientes WHERE id IN (%s,%s)", (c_alto, c_bajo))
        cur.execute("DELETE FROM proveedores WHERE id_proveedor=%s", (p_alto,))
        cur.execute("DELETE l FROM aeat_declaracion_lineas l JOIN aeat_declaraciones d "
                    "ON d.id=l.id_declaracion WHERE d.id_empresa=%s AND d.ejercicio=%s", (E, EJ))
        cur.execute("DELETE FROM aeat_declaraciones WHERE id_empresa=%s AND ejercicio=%s", (E, EJ))
        conn.commit()


# ── Umbral + agrupación por tercero ──────────────────────────────────────────
def test_umbral_excluye_pequenos(datos):
    m = M347.Modelo347(EJ, id_empresa=E)
    nifs = {d.nif for d in m.declarados}
    assert "C1111111X" in nifs and "B33333333" in nifs    # sobre umbral
    assert "C2222222Y" not in nifs                          # bajo umbral, excluido
    assert any(d.nif == "C2222222Y" for d in m.excluidos)


def test_desglose_trimestral(datos):
    m = M347.Modelo347(EJ, id_empresa=E)
    cli = next(d for d in m.declarados if d.nif == "C1111111X")
    assert cli.clave == "B" and cli.t1 == 2000.0 and cli.t3 == 1500.0 and cli.t2 == 0.0 and cli.t4 == 0.0
    assert round(cli.t1 + cli.t2 + cli.t3 + cli.t4, 2) == cli.total == 3500.0   # T1+..+T4 = total
    prov = next(d for d in m.declarados if d.nif == "B33333333")
    assert prov.clave == "A" and prov.t4 == 4840.0 and prov.total == 4840.0


def test_casillas_agregadas(datos):
    m = M347.Modelo347(EJ, id_empresa=E)
    cas = {c["casilla"]: c["importe"] for c in m.casillas() if c["casilla"] in ("01", "02")}
    assert cas["01"] == 2                                   # 2 declarados sobre umbral
    assert cas["02"] == round(3500.0 + 4840.0, 2)          # total declarado
    assert m.resultado == 8340.0


# ── Persistencia + auditoría + idempotencia ──────────────────────────────────
def test_persiste_audita_idempotente(db, datos):
    r1 = M347.generar(EJ, id_empresa=E)
    assert r1["ok"] and r1["resultado"] == 8340.0 and len(r1["declarados"]) == 2
    d = B.obtener_declaracion(r1["id"], id_empresa=E)
    assert d["modelo"] == "347" and d["periodo"] == "0A" and d["estado"] == ST.GENERADO and d["hash"]
    r2 = M347.generar(EJ, id_empresa=E)
    assert r2["id"] == r1["id"]
    assert len(B.listar_declaraciones(modelo="347", ejercicio=EJ, id_empresa=E)) == 1
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM auditoria_logs WHERE accion='AEAT_347_GENERADO'")
        assert (cur.fetchone()[0] or 0) >= 1


def test_pdf_export(datos):
    r = M347.generar(EJ, id_empresa=E)
    assert r["pdf"] and os.path.exists(r["pdf"])
    d = B.obtener_declaracion(r["id"], id_empresa=E)
    js = X.a_json(d); cs = X.a_csv(d)
    assert '"modelo": "347"' in js
    assert "C1111111X" in cs and "T1=" in cs and "B33333333" in cs   # NIF + trimestres visibles


def test_multiempresa(db, datos, fab):
    emp2 = fab.empresa("347 B")
    m2 = M347.Modelo347(EJ, id_empresa=emp2)
    assert m2.declarados == [] and m2.resultado == 0.0
