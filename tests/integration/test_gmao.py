"""
GMAO — activos, planes preventivos (genera OT), OT ciclo + repuestos por KARDEX + costes,
KPIs (MTTR/MTBF/disponibilidad) e IA predictiva (riesgo de averia). RBAC.
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID

E = EMPRESA_DEFAULT_ID


def _art(db, *codigos):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for c in codigos:
            cur.execute("INSERT IGNORE INTO articulos (codigo, nombre, id_empresa) VALUES (%s,%s,%s)", (c, c, E))
        conn.commit()


@pytest.fixture
def limpia(db):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("ot_recursos", "ot_tareas", "costes_ot", "ordenes_trabajo", "planes_tareas",
                  "planes_mantenimiento", "activos_historial", "activos_garantias", "activos_documentos", "activos"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (E,))
        conn.commit()


def test_activos_ficha_historial(db, limpia):
    from src.services.gmao import activos
    cod = f"A_{uuid.uuid4().hex[:5]}"
    aid = activos.crear_activo(cod, "Maquina", tipo="maquinaria", numero_serie="SN1", criticidad="alta",
                               id_empresa=E)
    assert aid
    activos.registrar_garantia(aid, proveedor="Prov", cobertura="2 años", id_empresa=E)
    assert activos.cambiar_estado(aid, "averiado", id_empresa=E)
    with pytest.raises(ValueError):
        activos.cambiar_estado(aid, "zzz", id_empresa=E)
    h = activos.historial(aid)
    assert any(e["evento"] == "ALTA" for e in h) and any(e["evento"] == "CAMBIO_ESTADO" for e in h)


def test_plan_genera_ot_preventiva(db, limpia):
    from src.services.gmao import ordenes, planes
    aid = None
    from src.services.gmao import activos
    aid = activos.crear_activo(f"A_{uuid.uuid4().hex[:5]}", "M", id_empresa=E)
    planes.crear_plan(f"PL_{uuid.uuid4().hex[:4]}", "Engrase", id_activo=aid, frecuencia="mensual",
                      proxima_fecha="2020-01-01", tareas=["t1", "t2"], id_empresa=E)
    creadas = planes.generar_ot_preventivas(id_empresa=E)
    assert creadas
    ot = ordenes.obtener(creadas[0])
    assert ot["tipo"] == "preventiva" and ot["estado"] == "abierta"


def test_ot_ciclo_repuestos_kardex(db, limpia):
    from src.db import lotes
    from src.services.gmao import activos, ordenes
    rep = f"R_{uuid.uuid4().hex[:5]}"
    _art(db, rep)
    lotes.registrar_entrada(rep, "L"+rep, 20, id_empresa=E)
    aid = activos.crear_activo(f"A_{uuid.uuid4().hex[:5]}", "M", id_empresa=E)
    ot = ordenes.crear_ot(tipo="correctiva", id_activo=aid, descripcion="Averia", id_empresa=E)
    ordenes.cambiar_estado(ot, "abierta", id_empresa=E)
    ordenes.asignar(ot, 1, id_empresa=E)
    ordenes.iniciar(ot, id_empresa=E)
    ordenes.añadir_repuesto(ot, rep, 5, coste_unitario=10, id_empresa=E)
    fin = ordenes.finalizar(ot, horas_mano_obra=2, coste_hora=30, id_empresa=E)
    assert fin["ok"]
    assert fin["costes"]["coste_real"] == 110.0   # 2*30 + 5*10
    assert lotes.stock_total_en_lotes(rep, id_empresa=E) == 15   # 20 - 5 consumidos por kardex


def test_transiciones_ot_invalidas(db, limpia):
    from src.services.gmao import ordenes
    ot = ordenes.crear_ot(tipo="correctiva", id_empresa=E)
    assert ordenes.finalizar(ot, id_empresa=E)["ok"] is False   # no se finaliza desde borrador
    with pytest.raises(ValueError):
        ordenes.crear_ot(tipo="zzz", id_empresa=E)


def test_kpis_e_ia(db, limpia):
    from src.services.gmao import activos, analitica, ordenes
    aid = activos.crear_activo(f"A_{uuid.uuid4().hex[:5]}", "M", criticidad="alta", id_empresa=E)
    for _ in range(3):
        ot = ordenes.crear_ot(tipo="correctiva", id_activo=aid, id_empresa=E)
        ordenes.cambiar_estado(ot, "abierta", id_empresa=E); ordenes.iniciar(ot, id_empresa=E)
        ordenes.finalizar(ot, id_empresa=E)
    k = analitica.kpis(id_empresa=E)
    assert k["averias_correctivas"] >= 3 and "disponibilidad_pct" in k
    r = analitica.riesgo_averia(aid, id_empresa=E)
    assert r["ok"] and r["riesgo"] in ("bajo", "medio", "alto")
    rec = analitica.averias_recurrentes(id_empresa=E, umbral=3)
    assert any(x["id_activo"] == aid for x in rec)


def test_rbac_gmao(db):
    from src.services.seguridad import catalogo
    catalogo.sincronizar_catalogo()
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo FROM permisos WHERE codigo IN ('gmao.ver','activos.gestionar','ot.crear')")
        enc = {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}
    assert {"gmao.ver", "activos.gestionar", "ot.crear"} <= enc
