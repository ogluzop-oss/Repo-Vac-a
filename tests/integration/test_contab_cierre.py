"""
F2.1 · Cierre contable formal — regularización, cierre, apertura y arrastre de saldos.

Verifica el ciclo PGC completo sobre el núcleo de asientos existente (sin tocarlo):
Σdebe=Σhaber, resultado a 129, saldos a cero tras el cierre, arrastre al ejercicio
siguiente, ejercicios consecutivos, trazabilidad y rechazo de intentos inválidos.
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


def _empresa_contable(db, fab, anio=2025):
    from src.services.contabilidad import cuentas as K
    emp = fab.empresa("CIERRE F2.1")
    fab.al_limpiar(lambda: _borra(db, emp))
    K.activar(emp, anio)
    return emp


def _movimientos_basicos(emp, anio):
    """Venta (ingreso 100 + IVA 21, cobrada en caja) y compra (gasto 60 + IVA 12.6,
    a proveedor). Resultado esperado = 100 - 60 = 40 (beneficio)."""
    from src.services.contabilidad.asientos import crear_asiento
    crear_asiento(f"{anio}-03-01", [
        {"codigo_cuenta": "570", "debe": 121.0}, {"codigo_cuenta": "700", "haber": 100.0},
        {"codigo_cuenta": "477", "haber": 21.0}], concepto="Venta", id_empresa=emp)
    crear_asiento(f"{anio}-04-01", [
        {"codigo_cuenta": "600", "debe": 60.0}, {"codigo_cuenta": "472", "debe": 12.6},
        {"codigo_cuenta": "400", "haber": 72.6}], concepto="Compra", id_empresa=emp)


# ── Regularización ────────────────────────────────────────────────────────────
def test_regularizacion_traslada_resultado_a_129(db, fab):
    from src.services.contabilidad import cierre as Ci, informes as I
    emp = _empresa_contable(db, fab); _movimientos_basicos(emp, 2025)
    r = Ci.regularizar(2025, usuario="T", id_empresa=emp)
    assert r and r["estado"] == "contabilizado"
    assert abs(r["total"] - 100.0) < 0.01                     # debe=haber=100
    # 700 y 600 quedan a cero; 129 recoge el beneficio (40, saldo acreedor → -40).
    assert abs(I.mayor("700", id_empresa=emp, anio=2025)["saldo"]) < 0.01
    assert abs(I.mayor("600", id_empresa=emp, anio=2025)["saldo"]) < 0.01
    assert abs(I.mayor("129", id_empresa=emp, anio=2025)["saldo"] + 40.0) < 0.01


def test_regularizacion_sin_pyg_devuelve_none(db, fab):
    from src.services.contabilidad import cierre as Ci
    emp = _empresa_contable(db, fab)
    assert Ci.regularizar(2025, id_empresa=emp) is None


# ── Cierre ────────────────────────────────────────────────────────────────────
def test_cierre_deja_todas_las_cuentas_a_cero(db, fab):
    from src.services.contabilidad import cierre as Ci, informes as I
    emp = _empresa_contable(db, fab); _movimientos_basicos(emp, 2025)
    Ci.regularizar(2025, id_empresa=emp)
    cie = Ci.asiento_cierre(2025, usuario="T", id_empresa=emp)
    assert cie and cie["estado"] == "contabilizado"
    bal = I.balance_sumas_saldos(id_empresa=emp, anio=2025)
    assert bal["cuadra"] is True
    assert all(abs(c["saldo"]) < 0.01 for c in bal["cuentas"])  # todo a cero en el ejercicio
    assert cie["tipo"] == "cierre" if "tipo" in cie else True


# ── Apertura + arrastre de saldos ─────────────────────────────────────────────
def test_cierre_formal_genera_apertura_con_arrastre(db, fab):
    from src.services.contabilidad import cierre as Ci, informes as I
    from src.services.contabilidad import cuentas as K
    emp = _empresa_contable(db, fab); _movimientos_basicos(emp, 2025)
    res = Ci.cerrar_ejercicio_formal(2025, usuario="T", id_empresa=emp)
    assert res["ok"] is True and res["destino"] == 2026
    assert res["regularizacion"] and res["cierre"] and res["apertura"]
    assert K.ejercicio_cerrado(2025, emp) is True
    # El ejercicio 2026 abre con los saldos arrastrados (activo=pasivo+PN).
    sit = I.balance_situacion(id_empresa=emp, anio=2026)
    assert sit["cuadra"] is True
    assert abs(sit["activo"] - 133.6) < 0.01                  # 570(121)+472(12.6)
    assert abs(sit["pasivo"] - 93.6) < 0.01                   # 477(21)+400(72.6)
    assert abs(sit["patrimonio_neto"] - 40.0) < 0.01          # 129 arrastrado
    # La apertura es un asiento trazable e identificable.
    ape = Ci.buscar_asiento(emp, 2026, "apertura")
    assert ape and ape["tipo"] == "apertura"
    assert ape["ref_origen"] == "ejercicio:2025->2026"
    assert ape["fecha"].strftime("%Y-%m-%d") == "2026-01-01"
    assert ape["usuario"] == "T" and ape["fecha_registro"] is not None


def test_arrastre_cuadra_debe_haber_en_apertura(db, fab):
    from src.services.contabilidad import cierre as Ci
    from src.services.contabilidad.asientos import obtener_asiento
    emp = _empresa_contable(db, fab); _movimientos_basicos(emp, 2025)
    res = Ci.cerrar_ejercicio_formal(2025, id_empresa=emp)
    a = obtener_asiento(res["apertura"]["id"], emp)
    assert abs(float(a["total_debe"]) - float(a["total_haber"])) < 0.01
    assert abs(float(a["total_debe"]) - 133.6) < 0.01


# ── Ejercicios consecutivos ───────────────────────────────────────────────────
def test_ejercicios_consecutivos(db, fab):
    from src.services.contabilidad import cierre as Ci
    from src.services.contabilidad import cuentas as K
    emp = _empresa_contable(db, fab); _movimientos_basicos(emp, 2025)
    Ci.cerrar_ejercicio_formal(2025, id_empresa=emp)
    # 2026 abrió con saldos patrimoniales; se puede cerrar también (sin PyG nuevo).
    res2 = Ci.cerrar_ejercicio_formal(2026, id_empresa=emp)
    assert res2["ok"] is True
    assert res2["regularizacion"] is None        # no hay grupos 6/7 en 2026
    assert res2["cierre"] and res2["apertura"]   # cierra y abre 2027
    assert K.ejercicio_cerrado(2026, emp) is True
    assert Ci.buscar_asiento(emp, 2027, "apertura") is not None


# ── Integridad / auditoría ────────────────────────────────────────────────────
def test_cadena_auditoria_valida_tras_cierre(db, fab):
    from src.services.contabilidad import cierre as Ci
    from src.services.contabilidad.asientos import cadena_auditoria_valida
    emp = _empresa_contable(db, fab); _movimientos_basicos(emp, 2025)
    Ci.cerrar_ejercicio_formal(2025, id_empresa=emp)
    assert cadena_auditoria_valida(emp, anio=2025) is True


# ── Intentos inválidos ────────────────────────────────────────────────────────
def test_no_recierra_ejercicio_cerrado(db, fab):
    from src.services.contabilidad import cierre as Ci
    emp = _empresa_contable(db, fab); _movimientos_basicos(emp, 2025)
    Ci.cerrar_ejercicio_formal(2025, id_empresa=emp)
    r2 = Ci.cerrar_ejercicio_formal(2025, id_empresa=emp)
    assert r2["ok"] is False and r2["motivo"] == "ya_cerrado"


def test_no_admite_asientos_en_ejercicio_cerrado(db, fab):
    from src.services.contabilidad import cierre as Ci
    from src.services.contabilidad.asientos import crear_asiento
    emp = _empresa_contable(db, fab); _movimientos_basicos(emp, 2025)
    Ci.cerrar_ejercicio_formal(2025, id_empresa=emp)
    nuevo = crear_asiento("2025-06-01", [{"codigo_cuenta": "570", "debe": 10.0},
                                         {"codigo_cuenta": "700", "haber": 10.0}], id_empresa=emp)
    assert nuevo is None                          # ejercicio bloqueado


def test_cierre_sin_ejercicio_devuelve_motivo(db, fab):
    from src.services.contabilidad import cierre as Ci
    emp = _empresa_contable(db, fab)
    r = Ci.cerrar_ejercicio_formal(2099, id_empresa=emp)
    assert r["ok"] is False and r["motivo"] == "sin_ejercicio"
