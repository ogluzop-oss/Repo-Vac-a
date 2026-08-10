"""
Tests · Click & Collect (recogida en tienda) — extensión de Comercio Digital.

Verifica el ciclo completo reutilizando la infraestructura existente: reserva (checkout único,
store-only), pago, preparación, recogida (única salida física por salida_stock_oficial), cancelación
con reembolso, expiración automática (24h), liberación del Reservation Ledger, multiempresa/multitienda,
eventos, RBAC y que NUNCA se mueve stock fuera de la recogida.
"""

from datetime import datetime, timedelta

import pytest

from src.services.comercio_digital import pickup, transacciones
from src.services.comercio_digital.inventario import reservas

pytestmark = pytest.mark.db

TIENDA = 1


def _stock(db, cod, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_tienda FROM articulos WHERE codigo=%s AND id_empresa=%s", (cod, emp))
        r = cur.fetchone()
        return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else None


def _purgar(db, emp):
    """Limpia el estado comercial del tenant (reservas/transacciones/pagos) para aislamiento total."""
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for tabla in ("cd_reservas", "cd_pagos", "transaccion_eventos", "transaccion_lineas",
                      "transaccion_comercial"):
            try:
                cur.execute(f"DELETE FROM {tabla} WHERE id_empresa=%s", (emp,))
            except Exception:
                pass
        conn.commit()


@pytest.fixture()
def art(db):
    """Crea un artículo con stock de tienda para un tenant; limpia artículo + estado comercial."""
    creados = []
    empresas = set()

    def _crear(cod, emp, stock=10):
        _purgar(db, emp)
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (cod, emp))
            cur.execute("INSERT INTO articulos (codigo,id_empresa,nombre,precio,Stock_tienda,"
                        "Stock_central) VALUES (%s,%s,%s,%s,%s,0)", (cod, emp, "Art CC", 9.9, stock))
            conn.commit()
        creados.append((cod, emp))
        empresas.add(emp)
        return cod
    yield _crear
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for cod, emp in creados:
            cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (cod, emp))
        conn.commit()
    for emp in empresas:
        _purgar(db, emp)


def _reservar(emp, cod, cant=3):
    return pickup.reservar(id_empresa=emp, id_tienda=TIENDA, cliente={"nombre": "Ana", "email": "a@b.c"},
                           lineas=[{"codigo": cod, "cantidad": cant}], canal="web")


# ── Ciclo feliz: reserva → pago → preparación → recogida ──────────────────────
def test_reserva_no_mueve_stock_y_reduce_ledger(art, db):
    emp = "CC-A"
    art("CCART1", emp, stock=10)
    r = _reservar(emp, "CCART1", 3)
    assert r["ok"] and r["estado"] == "CONFIRMADA"
    # Reserva en la TIENDA seleccionada (nunca central), sin mover stock físico.
    act = reservas.activas(r["id_tx"], emp)
    assert act and act[0]["bucket"] == "tienda_activa" and act[0]["cantidad"] == 3
    assert _stock(db, "CCART1", emp) == 10                 # stock físico intacto


def test_ciclo_recogida_ejecuta_salida_oficial(art, db):
    emp = "CC-B"
    art("CCART2", emp, stock=10)
    tx = _reservar(emp, "CCART2", 4)["id_tx"]
    assert pickup.pagar(tx, id_empresa=emp)["estado"] == "PAGADA"
    assert _stock(db, "CCART2", emp) == 10                 # el pago NO mueve stock
    assert pickup.preparar(tx, id_empresa=emp, usuario={"perfil": "GERENTE"})["ok"]
    assert _stock(db, "CCART2", emp) == 10                 # preparar NO mueve stock
    rec = pickup.recoger(tx, id_empresa=emp, usuario={"perfil": "GERENTE"})
    assert rec["ok"] and rec["estado"] == "FINALIZADA" and rec["salidas_stock"] >= 1
    assert _stock(db, "CCART2", emp) == 6                  # salida física SOLO en la recogida (10-4)
    assert (transacciones.obtener(tx, emp) or {}).get("estado") == "FACTURADA"


# ── Cancelación por cliente: libera reserva + reembolso, sin mover stock ──────
def test_cancelacion_libera_y_reembolsa(art, db):
    emp = "CC-C"
    art("CCART3", emp, stock=10)
    tx = _reservar(emp, "CCART3", 2)["id_tx"]
    pickup.pagar(tx, id_empresa=emp)
    res = pickup.cancelar(tx, id_empresa=emp, usuario={"perfil": "GERENTE"})
    assert res["ok"] and res["estado"] == "CANCELADA"
    assert res["reservas_liberadas"] >= 1
    assert res["reembolso"] and res["reembolso"]["estado"] == "reembolsado"
    assert _stock(db, "CCART3", emp) == 10                 # nunca se movió stock
    assert not reservas.activas(tx, emp)                    # ledger liberado


# ── Expiración automática (24h) vía Scheduler ─────────────────────────────────
def test_expiracion_automatica(art, db):
    emp = "CC-D"
    art("CCART4", emp, stock=10)
    tx = _reservar(emp, "CCART4", 1)["id_tx"]
    pickup.pagar(tx, id_empresa=emp)
    # Simula que han pasado más de 24h.
    r = pickup.expirar_vencidas(id_empresa=emp, ahora=datetime.now() + timedelta(hours=25))
    assert r["expiradas"] >= 1
    assert (transacciones.obtener(tx, emp) or {}).get("estado") == "EXPIRADA"
    assert not reservas.activas(tx, emp)                    # reserva liberada
    assert _stock(db, "CCART4", emp) == 10                 # sin mover stock
    assert pickup.registrar_job() is True                   # reutiliza el Scheduler


def test_expiracion_no_toca_antes_de_plazo(art, db):
    emp = "CC-E"
    art("CCART5", emp, stock=10)
    tx = _reservar(emp, "CCART5", 1)["id_tx"]
    pickup.pagar(tx, id_empresa=emp)
    r = pickup.expirar_vencidas(id_empresa=emp, ahora=datetime.now())   # aún en plazo
    assert (transacciones.obtener(tx, emp) or {}).get("estado") == "PAGADA"


# ── Multiempresa ──────────────────────────────────────────────────────────────
def test_multiempresa_aislado(art, db):
    art("CCART6F", "CC-F", stock=10)
    art("CCART6G", "CC-G", stock=10)
    tx_f = _reservar("CC-F", "CCART6F", 1)["id_tx"]
    pickup.pagar(tx_f, id_empresa="CC-F")
    # Expirar en OTRA empresa no debe afectar a CC-F.
    pickup.expirar_vencidas(id_empresa="CC-G", ahora=datetime.now() + timedelta(hours=25))
    assert (transacciones.obtener(tx_f, "CC-F") or {}).get("estado") == "PAGADA"


# ── RBAC + garantías ──────────────────────────────────────────────────────────
def test_rbac_preparar_denegado(art, db):
    emp = "CC-H"
    art("CCART7", emp, stock=10)
    tx = _reservar(emp, "CCART7", 1)["id_tx"]
    pickup.pagar(tx, id_empresa=emp)
    sin_permiso = {"perfil": "SIN", "id": "x"}
    r = pickup.preparar(tx, id_empresa=emp, usuario=sin_permiso)
    assert r.get("error") == "forbidden" and r.get("permiso") == "pickup.preparar"


def test_descriptor_garantias():
    d = pickup.descriptor()
    assert d["motor_nuevo"] is False and d["mueve_stock_fuera_de_recogida"] is False
    assert "salida_stock_oficial" in d["reutiliza"]
    assert "EXPIRADA" in d["estados"]
    assert set(d["eventos"]) >= {"PICKUP_RESERVED", "PICKUP_COLLECTED", "PICKUP_EXPIRED",
                                 "PICKUP_REFUNDED"}


def test_estado_expirada_en_catalogo_transacciones():
    assert "EXPIRADA" in transacciones.ESTADOS
    assert "EXPIRADA" in transacciones.TRANSICIONES["PAGADA"]
