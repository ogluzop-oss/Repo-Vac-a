"""
Tesorería · FASE 11 — Auditoría (cada operación deja traza en auditoria_logs).
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import tesoreria as T, vencimientos as V, pagos_proveedor as PP, sepa as S
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant

E = EMPRESA_DEFAULT_ID
IBAN = "ES9121000418450200051332"
IBAN2 = "DE89370400440532013000"


def _acciones(db, desde_id):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT accion, tabla_afectada FROM auditoria_logs WHERE id>%s", (desde_id,))
        return [(r[0] if not isinstance(r, dict) else r["accion"]) for r in cur.fetchall()]


def _max_id(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(id),0) FROM auditoria_logs")
        r = cur.fetchone()
        return r[0] if not isinstance(r, dict) else list(r.values())[0]


def test_auditoria_operaciones_tesoreria(db):
    base = _max_id(db)
    creados = {"cuentas": [], "remesas": []}
    with contexto_tenant(E, None):
        cid = T.crear_cuenta("Audit", IBAN, id_empresa=E); creados["cuentas"].append(cid)
        T.registrar_movimiento("COBRO", 10, id_cuenta=cid, id_empresa=E)
        vid = V.crear_vencimiento("PAGO", 20, "2026-12-31", origen="manual",
                                  id_documento="AU" + uuid.uuid4().hex[:6], id_empresa=E)
        rid = S.crear_remesa("TRANSFER", id_cuenta=cid, id_empresa=E); creados["remesas"].append(rid)
    try:
        acc = _acciones(db, base)
        assert "alta_cuenta_bancaria" in acc
        assert "movimiento_tesoreria" in acc
        assert "alta_vencimiento" in acc
        assert "crea_remesa" in acc
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM remesas_sepa WHERE id=%s", (rid,))
            cur.execute("DELETE FROM vencimientos WHERE id=%s", (vid,))
            cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta=%s", (cid,))
            cur.execute("DELETE FROM cuentas_bancarias WHERE id=%s", (cid,))
            conn.commit()
