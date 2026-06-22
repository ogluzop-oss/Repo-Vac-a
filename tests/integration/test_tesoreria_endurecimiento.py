"""
Tesorería · Endurecimiento — anti-duplicación, idempotencia, recuperación.

Cubre los riesgos residuales de la auditoría de robustez:
  • doble conciliación (línea o movimiento reutilizados)
  • línea de extracto duplicada (UNIQUE id_extracto+hash)
  • re-emisión / ejecución múltiple de remesa SEPA
  • movimiento de tesorería sin asiento tras fallo (recuperación)
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import tesoreria as T, conciliacion_bancaria as CB, sepa as S
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant
from src.services.contabilidad import cuentas as K
from src.services.tesoreria import conciliacion as CC, sepa as SEPA
from src.services.tesoreria import contabilidad as TC

E = EMPRESA_DEFAULT_ID
IBAN = "ES9121000418450200051332"
IBAN2 = "DE89370400440532013000"


@pytest.fixture
def cuenta(db):
    cid = T.crear_cuenta("End", IBAN, bic="CAIXESBBXXX", saldo_inicial=0, id_empresa=E)
    yield cid
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM conciliaciones WHERE id_empresa=%s", (E,))
        cur.execute("DELETE FROM extracto_lineas WHERE id_empresa=%s", (E,))
        cur.execute("DELETE FROM extractos_bancarios WHERE id_cuenta=%s", (cid,))
        cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta=%s", (cid,))
        cur.execute("DELETE FROM cuentas_bancarias WHERE id=%s", (cid,))
        conn.commit()


# ── Doble conciliación ────────────────────────────────────────────────────────
def test_no_doble_conciliacion(cuenta):
    m1 = T.registrar_movimiento("COBRO", 100, id_cuenta=cuenta, fecha="2026-05-10", id_empresa=E)
    csv = "fecha;importe;concepto\n2026-05-10;100,00;Cobro\n2026-05-10;100,00;Cobro2\n"
    imp = CC.importar_extracto(csv, "CSV", id_cuenta=cuenta, id_empresa=E)
    lineas = CB.listar_lineas(imp["id_extracto"], id_empresa=E)
    assert CC.conciliar(lineas[0]["id"], m1, id_empresa=E)
    # misma línea otra vez → rechazada
    assert CC.conciliar(lineas[0]["id"], m1, id_empresa=E) is False
    # otra línea contra el MISMO movimiento → rechazada (movimiento ya usado)
    assert CC.conciliar(lineas[1]["id"], m1, id_empresa=E) is False


def test_linea_extracto_no_duplica(cuenta):
    imp = CC.importar_extracto("fecha;importe;concepto\n2026-05-12;10,00;X\n", "CSV",
                               id_cuenta=cuenta, id_empresa=E)
    eid = imp["id_extracto"]
    n0 = len(CB.listar_lineas(eid, id_empresa=E))
    # dos inserciones IDÉNTICAS (mismo hash) → una sola fila (dedup app + UNIQUE 0051)
    a = CB.anadir_linea(eid, "2026-06-01", 10.00, concepto="Y", referencia="R", id_empresa=E)
    b = CB.anadir_linea(eid, "2026-06-01", 10.00, concepto="Y", referencia="R", id_empresa=E)
    assert a == b
    assert len(CB.listar_lineas(eid, id_empresa=E)) == n0 + 1


# ── Remesa SEPA: idempotencia / ejecución múltiple ───────────────────────────
def test_remesa_no_reemite(db, cuenta):
    rid = S.crear_remesa("TRANSFER", id_cuenta=cuenta, id_empresa=E)
    try:
        S.anadir_operacion(rid, "Prov", IBAN2, 50, concepto="F1", id_empresa=E)
        r1 = SEPA.generar_xml(rid, id_empresa=E)
        r2 = SEPA.generar_xml(rid, id_empresa=E)
        assert r1["ok"] and r2.get("idempotente") and r1["mensaje_id"] == r2["mensaje_id"]
        # transición legal hasta ejecutada; luego retroceso prohibido
        S.cambiar_estado(rid, "aceptada", id_empresa=E)
        S.cambiar_estado(rid, "ejecutada", fecha_ejecucion="2026-06-30", id_empresa=E)
        with pytest.raises(ValueError):
            S.cambiar_estado(rid, "emitida", id_empresa=E)        # no ejecución/re-emisión múltiple
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM remesa_lineas WHERE id_remesa=%s", (rid,))
            cur.execute("DELETE FROM remesas_sepa WHERE id=%s", (rid,))
            conn.commit()


# ── Recuperación: movimiento sin asiento tras fallo ──────────────────────────
def test_recuperacion_movimiento_sin_asiento(db, cuenta):
    K.activar(E)
    with contexto_tenant(E, None):
        mid = T.registrar_movimiento("COBRO", 77, id_cuenta=cuenta, fecha="2026-06-05", id_empresa=E)
    # Simula fallo entre commit del movimiento y su asiento: borra el asiento creado.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM contab_asientos WHERE id_empresa=%s AND ref_origen=%s", (E, f"tes:{mid}"))
        conn.commit()
    pend = TC.reparar_tesoreria_pendiente(E, aplicar=False)
    assert pend["pendientes"] >= 1
    rep = TC.reparar_tesoreria_pendiente(E, aplicar=True)
    assert rep["reparados"] >= 1
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM contab_asientos WHERE id_empresa=%s AND ref_origen=%s "
                    "AND estado<>'anulado'", (E, f"tes:{mid}"))
        n = cur.fetchone()[0]
    assert n == 1
    # idempotente: re-reparar no crea otro
    TC.reparar_tesoreria_pendiente(E, aplicar=True)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM contab_asientos WHERE id_empresa=%s AND ref_origen=%s "
                    "AND estado<>'anulado'", (E, f"tes:{mid}"))
        assert cur.fetchone()[0] == 1
