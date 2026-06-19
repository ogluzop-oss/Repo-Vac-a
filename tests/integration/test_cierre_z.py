"""
F2.2 · Cierre Z formal de caja — resumen, arqueo, trazabilidad y documento.

Usa ventas/devoluciones reales (sin mocks). Cada test aísla sus datos con una caja
única (las ventas no llevan id_empresa; el filtro real es fecha+caja).
"""

import os

import pytest

pytestmark = pytest.mark.db

_FECHA = "2031-06-15"


def _venta(db, fab, total, forma, caja, fecha=_FECHA):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO ventas (fecha, total, forma_pago, numero_caja) "
                    "VALUES (%s,%s,%s,%s)", (f"{fecha} 12:00:00", total, forma, caja))
        conn.commit()


def _devolucion(db, fab, total, forma, caja, fecha=_FECHA):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO devoluciones (fecha, total_reembolso, forma_reembolso, numero_caja) "
                    "VALUES (%s,%s,%s,%s)", (f"{fecha} 13:00:00", total, forma, caja))
        conn.commit()


def _limpia_caja(db, caja, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ventas WHERE numero_caja=%s", (caja,))
        cur.execute("DELETE FROM devoluciones WHERE numero_caja=%s", (caja,))
        cur.execute("DELETE FROM documentos_registro WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM cierres_z WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _setup(db, fab, caja):
    emp = fab.empresa("CIERRE Z")
    fab.al_limpiar(lambda: _limpia_caja(db, caja, emp))
    return emp


# ── Generación + totales ──────────────────────────────────────────────────────
def test_genera_cierre_z_totales(db, fab):
    from src.services.tpv import cierre_z as Z
    caja = 7001; emp = _setup(db, fab, caja)
    _venta(db, fab, 121.0, "efectivo", caja)
    _venta(db, fab, 242.0, "tarjeta", caja)
    _devolucion(db, fab, 21.0, "efectivo", caja)
    z = Z.generar_cierre_z(_FECHA, importe_declarado=150.0, usuario="CAJERO",
                           id_empresa=emp, caja=caja, fondo_inicial=50.0, generar_pdf=False)
    assert z is not None
    assert abs(float(z["ventas_brutas"]) - 363.0) < 0.01
    assert abs(float(z["devoluciones"]) - 21.0) < 0.01
    assert abs(float(z["total_cobrado"]) - 342.0) < 0.01
    assert abs(float(z["base"]) + float(z["iva"]) - 342.0) < 0.02   # IVA derivado del neto
    import json
    cobros = json.loads(z["desglose_cobros"])
    assert abs(cobros["efectivo"] - 100.0) < 0.01   # 121 - 21
    assert abs(cobros["tarjeta"] - 242.0) < 0.01
    assert z["numero"] == 1 and z["hash_audit"]


# ── Arqueo ────────────────────────────────────────────────────────────────────
def test_arqueo_cuadrado(db, fab):
    from src.services.tpv import cierre_z as Z
    caja = 7002; emp = _setup(db, fab, caja)
    _venta(db, fab, 100.0, "efectivo", caja)
    z = Z.generar_cierre_z(_FECHA, importe_declarado=100.0, id_empresa=emp, caja=caja,
                           fondo_inicial=0.0, generar_pdf=False)
    assert z["estado"] == "CUADRADO" and abs(float(z["diferencia"])) < 0.01
    assert abs(float(z["importe_esperado"]) - 100.0) < 0.01


def test_arqueo_descuadre(db, fab):
    from src.services.tpv import cierre_z as Z
    caja = 7003; emp = _setup(db, fab, caja)
    _venta(db, fab, 200.0, "efectivo", caja)
    z = Z.generar_cierre_z(_FECHA, importe_declarado=190.0, id_empresa=emp, caja=caja,
                           fondo_inicial=0.0, generar_pdf=False)
    assert z["estado"] == "DESCUADRE"
    assert abs(float(z["diferencia"]) + 10.0) < 0.01    # declarado - esperado = -10


def test_devoluciones_reducen_efectivo_esperado(db, fab):
    from src.services.tpv import cierre_z as Z
    caja = 7004; emp = _setup(db, fab, caja)
    _venta(db, fab, 300.0, "efectivo", caja)
    _devolucion(db, fab, 50.0, "efectivo", caja)
    z = Z.generar_cierre_z(_FECHA, importe_declarado=250.0, id_empresa=emp, caja=caja,
                           generar_pdf=False)
    # esperado = 300 - 50 = 250 → cuadrado
    assert abs(float(z["importe_esperado"]) - 250.0) < 0.01 and z["estado"] == "CUADRADO"


# ── Integridad documental ─────────────────────────────────────────────────────
def test_integridad_documental(db, fab):
    from src.services.tpv import cierre_z as Z
    caja = 7005; emp = _setup(db, fab, caja)
    _venta(db, fab, 121.0, "efectivo", caja)
    z = Z.generar_cierre_z(_FECHA, importe_declarado=121.0, usuario="C", id_empresa=emp,
                           caja=caja, generar_pdf=True)
    ruta = z["ruta_pdf"]
    assert ruta and os.path.exists(ruta)
    fab.al_limpiar(lambda: os.path.exists(ruta) and os.remove(ruta))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM documentos_registro WHERE referencia=%s",
                    (f"cierre_z:{z['id']}",))
        assert (cur.fetchone()[0] or 0) >= 1     # indexado en el centro documental


# ── Trazabilidad / inmutabilidad ──────────────────────────────────────────────
def test_inmutable_idempotente_y_cadena(db, fab):
    from src.services.tpv import cierre_z as Z
    caja = 7006; emp = _setup(db, fab, caja)
    _venta(db, fab, 100.0, "efectivo", caja)
    z1 = Z.generar_cierre_z(_FECHA, importe_declarado=100.0, id_empresa=emp, caja=caja,
                            generar_pdf=False)
    z2 = Z.generar_cierre_z(_FECHA, importe_declarado=999.0, id_empresa=emp, caja=caja,
                            generar_pdf=False)
    assert z2.get("duplicado") is True and z2["numero"] == z1["numero"]
    assert float(z2["importe_declarado"]) == float(z1["importe_declarado"])   # no se altera
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cierres_z WHERE id_empresa=%s", (emp,))
        assert cur.fetchone()[0] == 1            # no duplica fila
    assert Z.cadena_z_valida(emp) is True


# ── No duplica contabilidad ───────────────────────────────────────────────────
def test_no_genera_asientos(db, fab):
    from src.services.tpv import cierre_z as Z
    caja = 7007; emp = _setup(db, fab, caja)
    _venta(db, fab, 121.0, "efectivo", caja)
    Z.generar_cierre_z(_FECHA, importe_declarado=121.0, id_empresa=emp, caja=caja,
                       generar_pdf=False)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM contab_asientos WHERE id_empresa=%s", (emp,))
        assert cur.fetchone()[0] == 0            # el Z no contabiliza (lo hace posting)
