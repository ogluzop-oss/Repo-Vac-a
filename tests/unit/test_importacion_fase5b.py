"""
Fase 5-B: histórico de ventas (para forecasting, sin tocar `ventas`), saldos de apertura (asiento contable),
tesorería (cuenta con saldo inicial) y documentos históricos (adjuntos). Integridad fiscal intacta.
"""

import datetime as dt

import pytest

from src.services import importacion as I


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _csv(tmp_path, contenido, nombre="f.csv"):
    ruta = tmp_path / nombre
    ruta.write_text(contenido, encoding="utf-8")
    return str(ruta)


# ── Histórico de ventas ───────────────────────────────────────────────────────
def test_ventas_historicas_carga_idempotente_y_forecasting(emp, db, fab, tmp_path):
    fab.al_limpiar(lambda: fab._borrar("ventas_historicas", "codigo_articulo", "VH-1"))
    d1 = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    d2 = (dt.date.today() - dt.timedelta(days=2)).isoformat()
    ruta = _csv(tmp_path, f"fecha;codigo;cantidad;importe\n{d1};VH-1;5;50\n{d2};VH-1;3;30\n")
    res = I.ejecutar(ruta, entidad=I.VENTAS_HIST, id_empresa=emp)
    assert res["ok"] and res["cargados"] == 2
    from src.services.prediccion import adaptadores, forecasting
    dias = {str(r["d"]) for r in adaptadores.ventas_hist_por_dia(emp, dias=30)}
    assert d1 in dias and d2 in dias
    # el forecasting consume el histórico importado (fill-gaps) sin romper
    assert isinstance(forecasting.predecir_ventas(emp, horizonte=3, dias_hist=30, emitir=False), dict)
    # idempotente: re-importar no duplica
    I.ejecutar(ruta, entidad=I.VENTAS_HIST, id_empresa=emp)
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ventas_historicas WHERE codigo_articulo='VH-1' AND id_empresa=%s",
                    (emp,))
        assert cur.fetchone()[0] == 2                          # idempotente (aislado por empresa)


# ── Saldos de apertura (asiento contable, doble partida) ──────────────────────
def test_saldos_apertura_asiento_cuadrado(emp, monkeypatch, tmp_path):
    import src.services.contabilidad.asientos as A
    cap = {}

    def fake(fecha, lineas, **kw):
        cap["lineas"] = lineas; cap["kw"] = kw
        td = sum(l["debe"] for l in lineas); th = sum(l["haber"] for l in lineas)
        return {"id": 1} if abs(td - th) < 0.01 and td > 0 else None

    monkeypatch.setattr(A, "crear_asiento", fake)
    ruta = _csv(tmp_path, "cuenta;debe;haber\n570000;1000;0\n100000;0;1000\n")
    res = I.ejecutar(ruta, entidad=I.SALDOS, id_empresa=emp)
    assert res["ok"] and res["cargados"] == 2
    assert sum(l["debe"] for l in cap["lineas"]) == sum(l["haber"] for l in cap["lineas"]) == 1000
    assert cap["kw"].get("tipo") == "apertura" and cap["kw"].get("idempotente") is True


def test_saldos_por_signo(emp, monkeypatch, tmp_path):
    import src.services.contabilidad.asientos as A
    cap = {}
    monkeypatch.setattr(A, "crear_asiento", lambda f, l, **k: (cap.update(l=l) or {"id": 1}))
    ruta = _csv(tmp_path, "cuenta;saldo\n570000;1000\n400000;-1000\n")
    I.ejecutar(ruta, entidad=I.SALDOS, id_empresa=emp)
    d = {x["cuenta"]: (x["debe"], x["haber"]) for x in cap["l"]}
    assert d["570000"] == (1000, 0) and d["400000"] == (0, 1000)      # saldo con signo → debe/haber


def test_saldos_descuadre_se_rechaza(emp, monkeypatch, tmp_path):
    import src.services.contabilidad.asientos as A
    monkeypatch.setattr(A, "crear_asiento", lambda *a, **k: None)      # el motor contable rechaza el descuadre
    ruta = _csv(tmp_path, "cuenta;debe;haber\n570000;1000;0\n100000;0;500\n")
    res = I.ejecutar(ruta, entidad=I.SALDOS, id_empresa=emp)
    assert res["ok"] is False and "cuadr" in res["error"].lower()


# ── Tesorería (cuenta bancaria + saldo inicial) ───────────────────────────────
def test_tesoreria_crea_cuenta_con_saldo(emp, db, fab, tmp_path):
    fab.al_limpiar(lambda: fab._borrar("cuentas_bancarias", "nombre_cuenta", "Caja Import"))
    ruta = _csv(tmp_path, "nombre;iban;saldo;banco\nCaja Import;ES9121000418450200051332;5000;Caixa\n")
    res = I.ejecutar(ruta, entidad=I.TESORERIA, id_empresa=emp)
    assert res["ok"] and res["cargados"] == 1
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT saldo_inicial FROM cuentas_bancarias WHERE nombre_cuenta='Caja Import' AND "
                    "id_empresa=%s", (emp,))
        r = cur.fetchone()
    assert r and float(r[0]) == 5000


def test_tesoreria_iban_invalido_da_error(emp, tmp_path):
    ruta = _csv(tmp_path, "nombre;iban\nCta Mala;ES000\n")
    res = I.ejecutar(ruta, entidad=I.TESORERIA, id_empresa=emp)
    assert res["ok"] is False                                          # IBAN inválido → sin cuenta creada


# ── Documentos históricos (adjuntos) ──────────────────────────────────────────
def test_documentos_historicos_se_registran(emp, fab, tmp_path):
    fab.al_limpiar(lambda: [fab._borrar("documentos_registro", "nombre", n)
                            for n in ("factura1.pdf", "factura2.pdf")])
    f1 = tmp_path / "factura1.pdf"; f1.write_bytes(b"%PDF-1.4 uno")
    f2 = tmp_path / "factura2.pdf"; f2.write_bytes(b"%PDF-1.4 dos")
    res = I.importar_documentos([str(f1), str(f2)], tipo="otros", id_empresa=emp)
    assert res["ok"] and res["registrados"] == 2
