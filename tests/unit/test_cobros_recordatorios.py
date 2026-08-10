"""
Tests del motor de RECORDATORIOS DE COBRO (dunning de clientes, migración 0171).

Cubre: detección de facturas pendientes (con email del cliente), niveles de escalado por días desde el
vencimiento, envío + idempotencia (no reenvía el mismo nivel) + escalado al siguiente nivel, simulación
(dry-run sin registrar) y el resumen para la GUI. Determinista: `ahora` inyectado.
"""

import datetime as dt

import pytest

from src.db import clientes as CLI
from src.db import facturas_cliente as FC
from src.services.facturacion import recordatorios as REC


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _cliente(fab, emp, email="moroso@test.com"):
    cid = CLI.crear_cliente("Moroso Test", email=email, id_empresa=emp)
    fab._borrar("clientes", "id", cid)
    return cid


def _factura(fab, emp, cid, importe=121, vence="2026-06-01"):
    fid = FC.crear_factura(id_cliente=cid, id_empresa=emp, tipo_documento="factura", fecha_vencimiento=vence,
                           lineas=[{"descripcion": "Servicio", "cantidad": 1, "precio_unitario": importe}])
    fab._borrar("cobros_recordatorios", "id_factura", fid)
    fab._borrar("facturas_cliente_lineas", "id_factura", fid)
    fab._borrar("facturas_cliente", "id_factura", fid)
    return fid


def test_niveles_escalado():
    assert REC.nivel_objetivo(-10) is None        # aún muy lejos del vencimiento
    assert REC.nivel_objetivo(-3)["nivel"] == 0    # aviso previo
    assert REC.nivel_objetivo(0)["nivel"] == 0
    assert REC.nivel_objetivo(1)["nivel"] == 1     # recordatorio
    assert REC.nivel_objetivo(10)["nivel"] == 2    # segundo
    assert REC.nivel_objetivo(30)["nivel"] == 3    # reclamación


def test_pendientes_con_email(fab, emp):
    cid = _cliente(fab, emp, email="cli@correo.com")
    fid = _factura(fab, emp, cid)
    p = [x for x in REC.pendientes(emp) if x["id_factura"] == fid]
    assert p and p[0]["cliente_email"] == "cli@correo.com"
    assert abs(float(p[0]["total"]) - 121) < 0.01


def test_procesar_idempotente_y_escala(fab, emp):
    cid = _cliente(fab, emp)
    fid = _factura(fab, emp, cid, vence="2026-06-01")
    # aviso previo (vencimiento -2 días)
    r0 = REC.procesar(emp, ahora=dt.datetime(2026, 5, 30))
    assert r0["por_nivel"].get(0, 0) >= 1
    # mismo día → no reenvía
    r0b = REC.procesar(emp, ahora=dt.datetime(2026, 5, 30))
    assert r0b["por_nivel"].get(0, 0) == 0
    # +3 días → nivel 1
    r1 = REC.procesar(emp, ahora=dt.datetime(2026, 6, 4))
    assert r1["por_nivel"].get(1, 0) >= 1
    # +20 días → nivel 3 (salta el 2 no enviado)
    r3 = REC.procesar(emp, ahora=dt.datetime(2026, 6, 21))
    assert r3["por_nivel"].get(3, 0) >= 1
    niveles = sorted(x["nivel"] for x in REC.historial(fid, emp))
    assert niveles == [0, 1, 3]


def test_dry_run_no_registra(fab, emp):
    cid = _cliente(fab, emp)
    fid = _factura(fab, emp, cid, vence="2020-01-01")   # muy vencida
    r = REC.procesar(emp, enviar=False)
    assert r["enviados"] >= 1
    assert REC.historial(fid, emp) == []                # no registró nada


def test_resumen(fab, emp):
    cid = _cliente(fab, emp)
    fid = _factura(fab, emp, cid, vence="2020-01-01")
    fila = [x for x in REC.resumen(emp) if x["id_factura"] == fid]
    assert fila
    assert fila[0]["pendiente_envio"] is True
    assert "Reclamaci" in fila[0]["nivel_actual"]       # muy vencida → reclamación
    assert fila[0]["ultimo_nivel"] == -1                # aún no se ha enviado nada
