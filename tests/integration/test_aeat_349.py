"""
AEAT · FASE 6 — Modelo 349 (operaciones intracomunitarias): entregas (E) / adquisiciones (A),
agrupación por NIF-IVA, exclusión de no-intracom, persistencia, auditoría, export, multiempresa.
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID
from src.services.aeat import base as B, estados as ST, exportacion as X, modelo_349 as M349

E = EMPRESA_DEFAULT_ID
EJ = 2037


def _cliente(db, nombre, nif, *, intra=0, nif_iva=None, pais="ES"):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO clientes (nombre, nif, id_empresa, es_intracomunitario, nif_iva, "
                    "pais_fiscal) VALUES (%s,%s,%s,%s,%s,%s)", (nombre, nif, E, intra, nif_iva, pais))
        cid = cur.lastrowid; conn.commit()
    return cid


def _proveedor(db, razon, cif, *, intra=0, nif_iva=None, pais="ES"):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO proveedores (id_empresa, razon_social, cif_nif, es_intracomunitario, "
                    "nif_iva, pais_fiscal) VALUES (%s,%s,%s,%s,%s,%s)",
                    (E, razon, cif, intra, nif_iva, pais))
        pid = cur.lastrowid; conn.commit()
    return pid


def _factura_cliente(db, id_cli, base, fecha):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO facturas_cliente (id_empresa, id_cliente, estado, base, iva, total, "
                    "fecha_emision) VALUES (%s,%s,'emitida',%s,0,%s,%s)", (E, id_cli, base, base, fecha))
        conn.commit()


def _factura_compra(db, id_prov, base, fecha):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO compras_facturas (id_empresa, id_proveedor, numero_factura, "
                    "fecha_factura, base, iva, total, estado) VALUES (%s,%s,%s,%s,%s,0,%s,'registrada')",
                    (E, id_prov, "I" + uuid.uuid4().hex[:6], fecha, base, base))
        conn.commit()


@pytest.fixture
def datos(db):
    # Cliente intracomunitario (Francia) → entrega clave E, 2 facturas
    c_ue = _cliente(db, "Client FR", "X1", intra=1, nif_iva="FR12345678901", pais="FR")
    _factura_cliente(db, c_ue, 5000, f"{EJ}-02-10")
    _factura_cliente(db, c_ue, 3000, f"{EJ}-06-10")
    # Cliente nacional → NO intracomunitario, excluido
    c_es = _cliente(db, "Cliente ES", "C9", intra=0, pais="ES")
    _factura_cliente(db, c_es, 9999, f"{EJ}-03-01")
    # Proveedor intracomunitario (Alemania) → adquisición clave A
    p_ue = _proveedor(db, "Lieferant DE", "Y1", intra=1, nif_iva="DE111111111", pais="DE")
    _factura_compra(db, p_ue, 4000, f"{EJ}-11-05")
    yield {"c_ue": c_ue, "c_es": c_es, "p_ue": p_ue}
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM facturas_cliente WHERE id_empresa=%s AND id_cliente IN (%s,%s)",
                    (E, c_ue, c_es))
        cur.execute("DELETE FROM compras_facturas WHERE id_empresa=%s AND id_proveedor=%s", (E, p_ue))
        cur.execute("DELETE FROM clientes WHERE id IN (%s,%s)", (c_ue, c_es))
        cur.execute("DELETE FROM proveedores WHERE id_proveedor=%s", (p_ue,))
        cur.execute("DELETE l FROM aeat_declaracion_lineas l JOIN aeat_declaraciones d "
                    "ON d.id=l.id_declaracion WHERE d.id_empresa=%s AND d.ejercicio=%s", (E, EJ))
        cur.execute("DELETE FROM aeat_declaraciones WHERE id_empresa=%s AND ejercicio=%s", (E, EJ))
        conn.commit()


# ── Operaciones intracom + exclusión de nacionales ───────────────────────────
def test_entregas_y_adquisiciones(datos):
    m = M349.Modelo349(EJ, id_empresa=E)
    nifs = {o.nif_iva for o in m.operadores}
    assert "FR12345678901" in nifs and "DE111111111" in nifs
    entrega = next(o for o in m.operadores if o.nif_iva == "FR12345678901")
    assert entrega.clave == "E" and entrega.pais == "FR" and entrega.base == 8000.0   # 5000+3000 agrupado
    adq = next(o for o in m.operadores if o.nif_iva == "DE111111111")
    assert adq.clave == "A" and adq.pais == "DE" and adq.base == 4000.0


def test_excluye_no_intracomunitario(datos):
    m = M349.Modelo349(EJ, id_empresa=E)
    # el cliente nacional (9999) no aparece
    assert all(o.base != 9999.0 for o in m.operadores)
    assert len(m.operadores) == 2


def test_agrupacion_por_nif_iva(datos):
    m = M349.Modelo349(EJ, id_empresa=E)
    fr = [o for o in m.operadores if o.nif_iva == "FR12345678901"]
    assert len(fr) == 1 and fr[0].base == 8000.0       # 2 facturas → 1 operador agrupado


def test_casillas(datos):
    m = M349.Modelo349(EJ, id_empresa=E)
    cas = {c["casilla"]: c["importe"] for c in m.casillas() if c["casilla"] in ("01", "02")}
    assert cas["01"] == 2 and cas["02"] == 12000.0     # 8000 + 4000
    assert m.resultado == 12000.0


# ── Persistencia + auditoría + idempotencia ──────────────────────────────────
def test_persiste_audita_idempotente(db, datos):
    r1 = M349.generar(EJ, id_empresa=E)
    assert r1["ok"] and r1["resultado"] == 12000.0 and len(r1["operadores"]) == 2
    d = B.obtener_declaracion(r1["id"], id_empresa=E)
    assert d["modelo"] == "349" and d["periodo"] == "0A" and d["estado"] == ST.GENERADO and d["hash"]
    r2 = M349.generar(EJ, id_empresa=E)
    assert r2["id"] == r1["id"]
    assert len(B.listar_declaraciones(modelo="349", ejercicio=EJ, id_empresa=E)) == 1
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM auditoria_logs WHERE accion='AEAT_349_GENERADO'")
        assert (cur.fetchone()[0] or 0) >= 1


def test_pdf_export(datos):
    r = M349.generar(EJ, id_empresa=E)
    assert r["pdf"] and os.path.exists(r["pdf"])
    d = B.obtener_declaracion(r["id"], id_empresa=E)
    js = X.a_json(d); cs = X.a_csv(d)
    assert '"modelo": "349"' in js
    assert "FR12345678901" in cs and "DE111111111" in cs and "clave E" in cs   # NIF-IVA/país/operación


def test_multiempresa(db, datos, fab):
    emp2 = fab.empresa("349 B")
    m2 = M349.Modelo349(EJ, id_empresa=emp2)
    assert m2.operadores == [] and m2.resultado == 0.0
