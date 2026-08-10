"""
Tests de conversión CRM → Factura (migración 0170).

Cubre: generación de una PROFORMA a partir de la oportunidad (valor = total con IVA incluido), enlace
oportunidad↔documento, IDEMPOTENCIA (no factura dos veces) y errores (sin cliente / sin valor / inexistente).
Reutiliza el motor de facturación existente (no hay factura fiscal 'emitida' automática).
"""

import pytest

from src.db import clientes as CLI
from src.db import facturas_cliente as FC
from src.services.crm import conversion as CONV
from src.services.crm import oportunidades as OP


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _cliente(fab, emp):
    cid = CLI.crear_cliente("Cliente Conv Test", nif="B12345678", id_empresa=emp)
    fab._borrar("clientes", "id", cid)
    return cid


def _oportunidad(fab, emp, **kw):
    oid = OP.crear_oportunidad(kw.pop("titulo", "Deal test"), id_empresa=emp, **kw)
    fab._borrar("crm_oportunidades", "id", oid)
    return oid


def test_convertir_genera_proforma(fab, emp, db):
    cid = _cliente(fab, emp)
    oid = _oportunidad(fab, emp, valor=1000, id_cliente=cid)
    r = CONV.convertir_a_factura(oid, id_empresa=emp)
    assert r["ok"] and not r["existente"] and r["tipo"] == "proforma"
    fid = r["id_factura"]
    fab._borrar("facturas_cliente_lineas", "id_factura", fid)
    fab._borrar("facturas_cliente", "id_factura", fid)
    f = FC.obtener_factura(fid, emp)
    assert f["tipo_documento"] == "proforma"
    assert str(f["id_cliente"]) == str(cid)
    # el valor de la oportunidad es el TOTAL del documento (IVA incluido)
    assert abs(float(f["total"]) - 1000) < 0.01
    # oportunidad enlazada
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT id_factura FROM crm_oportunidades WHERE id=%s", (oid,))
        assert cur.fetchone()[0] == fid


def test_idempotente(fab, emp):
    cid = _cliente(fab, emp)
    oid = _oportunidad(fab, emp, valor=500, id_cliente=cid)
    r1 = CONV.convertir_a_factura(oid, id_empresa=emp)
    fid = r1["id_factura"]
    fab._borrar("facturas_cliente_lineas", "id_factura", fid)
    fab._borrar("facturas_cliente", "id_factura", fid)
    r2 = CONV.convertir_a_factura(oid, id_empresa=emp)
    assert r2["ok"] and r2["existente"] is True and r2["id_factura"] == fid


def test_sin_cliente_error(fab, emp):
    oid = _oportunidad(fab, emp, valor=500)          # sin id_cliente
    r = CONV.convertir_a_factura(oid, id_empresa=emp)
    assert r["ok"] is False and "cliente" in r["error"]


def test_sin_valor_error(fab, emp):
    cid = _cliente(fab, emp)
    oid = _oportunidad(fab, emp, valor=0, id_cliente=cid)
    r = CONV.convertir_a_factura(oid, id_empresa=emp)
    assert r["ok"] is False and "valor" in r["error"]


def test_oportunidad_inexistente(emp):
    r = CONV.convertir_a_factura(999999999, id_empresa=emp)
    assert r["ok"] is False and "inexistente" in r["error"]


# ── CRM → Proyecto (migración 0173) ───────────────────────────────────────────
def test_convertir_a_proyecto(fab, emp, db):
    from src.services.proyectos import proyectos as PROY
    cid = _cliente(fab, emp)
    oid = _oportunidad(fab, emp, valor=8000, id_cliente=cid)
    r = CONV.convertir_a_proyecto(oid, id_empresa=emp)
    assert r["ok"] and not r["existente"]
    pid = r["id_proyecto"]
    for t in ("proyecto_costes", "proyecto_horas", "proyecto_tareas"):
        fab._borrar(t, "id_proyecto", pid)
    fab._borrar("proyectos", "id", pid)
    p = PROY.obtener_proyecto(pid, id_empresa=emp)
    assert float(p["presupuesto"]) == 8000 and str(p["id_cliente"]) == str(cid)
    # enlace + idempotencia
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT id_proyecto FROM crm_oportunidades WHERE id=%s", (oid,))
        assert cur.fetchone()[0] == pid
    r2 = CONV.convertir_a_proyecto(oid, id_empresa=emp)
    assert r2["existente"] is True and r2["id_proyecto"] == pid
