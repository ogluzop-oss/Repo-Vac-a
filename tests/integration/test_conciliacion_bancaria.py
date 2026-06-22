"""
Tesorería · FASE 8 — Conciliación bancaria (parsers CSV/N43/CAMT + import + emparejamiento).
"""

import pytest

pytestmark = pytest.mark.db

from src.db import tesoreria as T
from src.db import conciliacion_bancaria as CB
from src.db.empresa import EMPRESA_DEFAULT_ID
from src.services.tesoreria import conciliacion as CC
from src.services.tesoreria import extractos as EX

E = EMPRESA_DEFAULT_ID
IBAN = "ES9121000418450200051332"


# ── Parsers (sin BD) ──────────────────────────────────────────────────────────
def test_parse_csv():
    csv = "fecha;importe;concepto;referencia\n2026-05-01;100,50;Ingreso;R1\n2026-05-02;-30,00;Recibo;R2\n"
    r = EX.parse_csv(csv)
    assert len(r) == 2
    assert r[0]["importe"] == 100.50 and r[1]["importe"] == -30.0
    assert r[0]["fecha"] == "2026-05-01"


def test_parse_camt053():
    xml = """<?xml version="1.0"?><Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
    <BkToCstmrStmt><Stmt><Ntry><Amt Ccy="EUR">200.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>
    <BookgDt><Dt>2026-05-03</Dt></BookgDt><AddtlNtryInf>Transferencia recibida</AddtlNtryInf></Ntry>
    <Ntry><Amt Ccy="EUR">45.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2026-05-04</Dt></BookgDt>
    <AddtlNtryInf>Comision</AddtlNtryInf></Ntry></Stmt></BkToCstmrStmt></Document>"""
    r = EX.parse_camt053(xml)
    assert len(r) == 2
    assert r[0]["importe"] == 200.0 and r[1]["importe"] == -45.0
    assert r[0]["fecha"] == "2026-05-03"


def test_parse_n43():
    # Cuaderno 43 reg.22: 22 + oficina(4) + fechaOp(6) + fechaValor(6) + cComún(2) + cPropio(3)
    # + debeHaber(1) + importe(14)  → 38 chars; rellenado a 80.
    linea22 = "22" + "0001" + "260505" + "260505" + "01" + "000" + "2" + "00000000012345"
    linea22 = linea22.ljust(80)
    r = EX.parse_n43(linea22 + "\n")
    assert len(r) == 1
    assert r[0]["importe"] == 123.45        # dh=2 (abono) → positivo
    assert r[0]["fecha"] == "2026-05-05"


# ── Importación + conciliación ────────────────────────────────────────────────
@pytest.fixture
def cuenta(db):
    cid = T.crear_cuenta("Conc", IBAN, saldo_inicial=0, id_empresa=E)
    yield cid
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM conciliaciones WHERE id_empresa=%s", (E,))
        cur.execute("DELETE FROM extracto_lineas WHERE id_empresa=%s", (E,))
        cur.execute("DELETE FROM extractos_bancarios WHERE id_cuenta=%s", (cid,))
        cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta=%s", (cid,))
        cur.execute("DELETE FROM cuentas_bancarias WHERE id=%s", (cid,))
        conn.commit()


def test_importar_y_conciliar_automatico(cuenta):
    # Movimiento real en tesorería que debe casar con la línea del extracto.
    T.registrar_movimiento("COBRO", 150.00, id_cuenta=cuenta, fecha="2026-05-10", id_empresa=E)
    csv = "fecha;importe;concepto\n2026-05-10;150,00;Cobro cliente\n2026-05-11;999,99;No casa\n"
    imp = CC.importar_extracto(csv, "CSV", id_cuenta=cuenta, id_empresa=E)
    assert imp["num_lineas"] == 2
    res = CC.conciliar_automatico(imp["id_extracto"], id_cuenta=cuenta, id_empresa=E)
    assert res["conciliadas"] == 1 and res["sin_match"] == 1
    # la línea sin match es una diferencia
    difs = CC.diferencias(imp["id_extracto"], id_empresa=E)
    assert len(difs) == 1 and float(difs[0]["importe"]) == 999.99


def test_conciliacion_manual_y_sugerencia(cuenta):
    mid = T.registrar_movimiento("PAGO", -75.00, id_cuenta=cuenta, fecha="2026-05-20", id_empresa=E)
    csv = "fecha;importe;concepto\n2026-05-21;-75,00;Recibo luz\n"
    imp = CC.importar_extracto(csv, "CSV", id_cuenta=cuenta, id_empresa=E)
    linea = CB.listar_lineas(imp["id_extracto"], id_empresa=E)[0]
    sug = CC.sugerir(linea["id"], id_cuenta=cuenta, id_empresa=E)
    assert any(s["id"] == mid for s in sug)         # el movimiento aparece como candidato
    assert CC.conciliar(linea["id"], mid, id_empresa=E)
    assert CB.listar_lineas(imp["id_extracto"], solo_no_conciliadas=True, id_empresa=E) == []
