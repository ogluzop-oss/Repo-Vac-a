"""
F4.5 · Integración nómina → contabilidad (cola E6).

encolar_nomina → procesar_cola → asiento 640/642 ↔ 476/4751/465 con cuadre exacto.
Alta idempotente de 4751, aislamiento multiempresa, contabilidad OFF y best-effort.
"""

import pytest

pytestmark = pytest.mark.db

from src.services.contabilidad import asientos as A, cuentas as K, posting as P


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE ap FROM contab_apuntes ap JOIN contab_asientos a ON a.id=ap.id_asiento "
                    "WHERE a.id_empresa=%s", (emp,))
        for t in ("contab_asientos", "contab_cola", "contab_cuentas", "contab_ejercicios",
                  "contab_config"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _empresa_contable(db, fab):
    emp = fab.empresa("F45 CONTAB")
    fab.al_limpiar(lambda: _borra(db, emp))
    K.activar(emp, 2026)
    return emp


# Magnitudes de prueba (cuadre): dev=2500, ss_e=750, ss_t=160, irpf=300
_DEV, _SSE, _SST, _IRPF = 2500.0, 750.0, 160.0, 300.0
_LIQ = round(_DEV - _SST - _IRPF, 2)   # 2040.0


def test_encolar_y_procesar_genera_asiento(db, fab):
    emp = _empresa_contable(db, fab)
    cid = P.encolar_nomina("E1-2026-06", "2026-06-30", _DEV, _SSE, _SST, _IRPF, id_empresa=emp)
    assert cid                                   # encolado
    res = P.procesar_cola(emp)
    assert res["asientos"] >= 1
    diario = A.listar_diario(emp, anio=2026)
    nom = [a for a in diario if (a.get("ref_origen") or "").startswith("nomina:")]
    assert len(nom) == 1


def test_asiento_cuadra_y_cuentas(db, fab):
    emp = _empresa_contable(db, fab)
    P.encolar_nomina("E2-2026-06", "2026-06-30", _DEV, _SSE, _SST, _IRPF, id_empresa=emp)
    P.procesar_cola(emp)
    a = [x for x in A.listar_diario(emp, anio=2026) if (x.get("ref_origen") or "").startswith("nomina:")][0]
    det = A.obtener_asiento(a["id"], emp)
    apuntes = {ap["codigo_cuenta"]: (float(ap["debe"]), float(ap["haber"])) for ap in det["apuntes"]}
    assert apuntes["640"] == (_DEV, 0.0)
    assert apuntes["642"] == (_SSE, 0.0)
    assert apuntes["476"] == (0.0, round(_SSE + _SST, 2))
    assert apuntes["4751"] == (0.0, _IRPF)
    assert apuntes["465"] == (0.0, _LIQ)
    # cuadre exacto
    assert round(float(det["total_debe"]), 2) == round(float(det["total_haber"]), 2)
    assert round(float(det["total_debe"]), 2) == round(_DEV + _SSE, 2)


def test_4751_se_crea_idempotente(db, fab):
    emp = _empresa_contable(db, fab)
    # tras activar (que ahora clona 4751 desde plan_pgc) existe; forzamos el caso "faltaba"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM contab_cuentas WHERE id_empresa=%s AND codigo='4751'", (emp,))
        conn.commit()
    assert K.obtener_cuenta("4751", emp) is None
    P.encolar_nomina("E3-2026-06", "2026-06-30", _DEV, _SSE, _SST, _IRPF, id_empresa=emp)
    P.procesar_cola(emp)
    c = K.obtener_cuenta("4751", emp)
    assert c and c["tipo"] == "pasivo"           # creada automáticamente
    # repetir no duplica ni falla
    P.encolar_nomina("E4-2026-06", "2026-06-30", _DEV, _SSE, _SST, _IRPF, id_empresa=emp)
    P.procesar_cola(emp)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM contab_cuentas WHERE id_empresa=%s AND codigo='4751'", (emp,))
        assert cur.fetchone()[0] == 1


def test_plan_pgc_incluye_4751_en_activar(db, fab):
    emp = _empresa_contable(db, fab)   # activar clona el plan
    assert K.obtener_cuenta("4751", emp) is not None


def test_contabilidad_desactivada_no_encola(db, fab):
    emp = fab.empresa("F45 OFF")
    fab.al_limpiar(lambda: _borra(db, emp))      # NO se activa contabilidad
    cid = P.encolar_nomina("X-2026-06", "2026-06-30", _DEV, _SSE, _SST, _IRPF, id_empresa=emp)
    assert cid is None                            # no-op si contabilidad inactiva
    assert P.procesar_cola(emp)["asientos"] == 0


def test_aislamiento_multiempresa(db, fab):
    emp1 = _empresa_contable(db, fab)
    emp2 = _empresa_contable(db, fab)
    P.encolar_nomina("A-2026-06", "2026-06-30", _DEV, _SSE, _SST, _IRPF, id_empresa=emp1)
    P.procesar_cola(emp1)
    # procesar emp2 no debe materializar el evento de emp1
    P.procesar_cola(emp2)
    d1 = [a for a in A.listar_diario(emp1, anio=2026) if (a.get("ref_origen") or "").startswith("nomina:")]
    d2 = [a for a in A.listar_diario(emp2, anio=2026) if (a.get("ref_origen") or "").startswith("nomina:")]
    assert len(d1) == 1 and len(d2) == 0


def test_best_effort_no_rompe_rrhh(db, fab, monkeypatch):
    """Si la contabilización falla, la persistencia de la nómina NO falla."""
    from src.rrhh.db import empleados as E
    from src.db import empresa as empmod
    emp = fab.empresa("F45 BE")
    fab.al_limpiar(lambda: _borra(db, emp))
    ctx = empmod.contexto_tenant(emp, None); ctx.__enter__()
    fab.al_limpiar(lambda: ctx.__exit__(None, None, None))
    eid = E.crear_empleado(id_empresa=emp, nombre="Ana", nif="90000000Z")
    # forzar fallo del encolado contable
    monkeypatch.setattr("src.services.contabilidad.posting.encolar_nomina",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    from src.rrhh import persistencia
    res = persistencia.registrar_generacion(
        "NÓMINA", {"nif": "90000000Z", "fecha": "30/06/2026", "salario": "2000",
                   "num_pagas": "14", "irpf_pct": "15", "grupo_cotizacion": "1"},
        ruta="x.pdf", id_empresa=emp)
    assert res == eid                             # la nómina se persistió pese al fallo contable
    from src.rrhh.db import nominas as N
    assert len(N.listar_nominas(eid, emp)) == 1
