"""
Cuentas Anuales (Balance de Situación, ECPN, Estado de Flujos de Efectivo) — computación real
sobre el ciclo de cierre formal existente (`cierre.cerrar_ejercicio_formal`), sin tablas
nuevas. Verifica: el balance cuadra (Activo = PN + Pasivo) tanto en un ejercicio abierto como
ya cerrado formalmente, el ECPN reconcilia inicial+movimientos=final, y el EFE (indirecto)
reconcilia con la variación real de efectivo (grupo 57x) — en dos ejercicios consecutivos
con arrastre de saldos.
"""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE ap FROM contab_apuntes ap JOIN contab_asientos a ON a.id=ap.id_asiento "
                    "WHERE a.id_empresa=%s", (emp,))
        for t in ("contab_asientos", "contab_cuentas", "contab_ejercicios", "contab_config"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _empresa_contable(db, fab, anio=2030):
    from src.services.contabilidad import cuentas as K
    emp = fab.empresa("CUENTAS ANUALES")
    fab.al_limpiar(lambda: _borra(db, emp))
    K.activar(emp, anio)
    return emp


def _movimientos(emp, anio):
    """Venta (ingreso 200 + IVA 42, cobrada en banco) y compra de existencias a crédito
    (gasto 80 + IVA 16.8, a proveedor, sin pagar — queda en 400). Resultado = 200-80=120."""
    from src.services.contabilidad.asientos import crear_asiento
    crear_asiento(f"{anio}-03-01", [
        {"codigo_cuenta": "572", "debe": 242.0}, {"codigo_cuenta": "700", "haber": 200.0},
        {"codigo_cuenta": "477", "haber": 42.0}], concepto="Venta", id_empresa=emp)
    crear_asiento(f"{anio}-04-01", [
        {"codigo_cuenta": "600", "debe": 80.0}, {"codigo_cuenta": "472", "debe": 16.8},
        {"codigo_cuenta": "400", "haber": 96.8}], concepto="Compra a crédito", id_empresa=emp)


# ── Balance de situación ──────────────────────────────────────────────────────────────────
def test_balance_cuadra_ejercicio_abierto(db, fab):
    from src.services.contabilidad import balance_situacion as B
    emp = _empresa_contable(db, fab); _movimientos(emp, 2030)
    bal = B.generar_balance(2030, id_empresa=emp)
    assert bal["cuadra"] is True and bal["advertencias"] == []
    assert bal["activo"]["total"] == bal["pn_pasivo"]["total"]
    # Activo: 572(242)+472(16.8)=258.8 ; Pasivo: 477(42)+400(96.8)=138.8 ; PN: 120 (resultado)
    assert abs(bal["activo"]["total"] - 258.8) < 0.01
    assert abs(bal["pn_pasivo"]["pasivo_corriente"]["total"] - 138.8) < 0.01
    assert abs(bal["resultado_del_ejercicio"] - 120.0) < 0.01
    assert bal["resultados_ejercicios_anteriores"] == 0.0     # primer ejercicio de la empresa


def test_balance_cuadra_tras_cierre_formal(db, fab):
    """Tras el cierre formal, `_saldos(anio)` del propio ejercicio queda a cero (por diseño
    de `cierre.asiento_cierre`) — `generar_balance` debe recuperar los saldos reales leyendo
    la apertura del ejercicio siguiente, y el resultado real desde la propia regularización."""
    from src.services.contabilidad import balance_situacion as B, cierre as Ci
    emp = _empresa_contable(db, fab); _movimientos(emp, 2030)
    res = Ci.cerrar_ejercicio_formal(2030, usuario="T", id_empresa=emp)
    assert res["ok"] is True
    bal = B.generar_balance(2030, id_empresa=emp)
    assert bal["cuadra"] is True
    assert abs(bal["activo"]["total"] - 258.8) < 0.01
    assert abs(bal["resultado_del_ejercicio"] - 120.0) < 0.01


def test_balance_segundo_ejercicio_arrastra_resultados_anteriores(db, fab):
    from src.services.contabilidad import balance_situacion as B, cierre as Ci
    emp = _empresa_contable(db, fab); _movimientos(emp, 2030)
    Ci.cerrar_ejercicio_formal(2030, id_empresa=emp)
    bal2031 = B.generar_balance(2031, id_empresa=emp)
    assert bal2031["cuadra"] is True
    assert abs(bal2031["resultados_ejercicios_anteriores"] - 120.0) < 0.01
    assert abs(bal2031["resultado_del_ejercicio"]) < 0.01       # sin actividad nueva en 2031


# ── ECPN ──────────────────────────────────────────────────────────────────────────────────
def test_ecpn_reconcilia_inicial_mas_movimientos_igual_final(db, fab):
    from src.services.contabilidad import cierre as Ci, ecpn as E
    emp = _empresa_contable(db, fab); _movimientos(emp, 2030)
    Ci.cerrar_ejercicio_formal(2030, id_empresa=emp)
    e = E.generar_ecpn(2031, id_empresa=emp)
    assert e["cuadra"] is True and e["advertencias"] == []
    assert abs(e["pn_inicial"] + e["total_movimientos"] - e["pn_final"]) < 0.01
    assert abs(e["pn_inicial"] - 120.0) < 0.01 and abs(e["pn_final"] - 120.0) < 0.01
    # El resultado de 2030 se traspasa de "resultado del ejercicio" a "resultados anteriores".
    assert abs(e["lineas"]["resultado_del_ejercicio"]["movimiento"] + 120.0) < 0.01
    assert abs(e["lineas"]["resultados_ejercicios_anteriores"]["movimiento"] - 120.0) < 0.01


# ── Estado de Flujos de Efectivo ──────────────────────────────────────────────────────────
def test_flujos_reconcilia_con_efectivo_real_primer_ejercicio(db, fab):
    from src.services.contabilidad import estado_flujos as F
    emp = _empresa_contable(db, fab); _movimientos(emp, 2030)
    f = F.generar_estado_flujos(2030, id_empresa=emp)
    assert f["cuadra"] is True
    assert abs(f["ajuste_conciliacion"]) < 0.01
    assert f["variacion_neta_calculada"] == f["variacion_neta_real_efectivo"]
    # Explotación: resultado 120 + Δcirculante (477 sube 42 e IVA soportado 472 sube 16.8
    # también cuentan como circulante operativo, al no haberse liquidado con Hacienda todavía;
    # 400 sube 96.8) = 120 - 16.8 + 96.8 + 42 = 242 (coincide con el efectivo cobrado real).
    assert abs(f["explotacion"]["total"] - 242.0) < 0.01
    assert abs(f["efectivo_final"] - 242.0) < 0.01               # 572 cobrado en banco
    assert f["inversion"]["total"] == 0.0 and f["financiacion"]["total"] == 0.0


def test_flujos_reconcilia_tras_cierre_formal_y_segundo_ejercicio(db, fab):
    from src.services.contabilidad import cierre as Ci, estado_flujos as F
    from src.services.contabilidad.asientos import crear_asiento
    emp = _empresa_contable(db, fab); _movimientos(emp, 2030)
    Ci.cerrar_ejercicio_formal(2030, id_empresa=emp)
    # 2031: cobra la mitad de lo adeudado a proveedores (pago real de caja).
    crear_asiento("2031-02-01", [{"codigo_cuenta": "400", "debe": 50.0},
                                 {"codigo_cuenta": "572", "haber": 50.0}],
                 concepto="Pago parcial a proveedor", id_empresa=emp)
    f = F.generar_estado_flujos(2031, id_empresa=emp)
    assert f["cuadra"] is True
    assert abs(f["ajuste_conciliacion"]) < 0.01
    assert abs(f["efectivo_final"] - 192.0) < 0.01                # 242 - 50
    # Pagar proveedores reduce el circulante operativo en 50 (salida de caja operativa).
    assert abs(f["explotacion"]["total"] + 50.0) < 0.01
