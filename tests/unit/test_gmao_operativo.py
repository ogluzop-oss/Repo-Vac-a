"""
Tests · GMAO OPERATIVO (cierre de brecha funcional).

Verifica el ciclo real que ahora expone la GUI operativa, ejecutando los servicios existentes:
Activo → OT correctiva (borrador→abierta→asignada→en_curso) → repuesto → finalización que CONSUME el
repuesto por el KARDEX OFICIAL (SALIDA_PRODUCCION, id_documento OT:<id>) y calcula costes; y el ciclo
PREVENTIVO (plan vencido → generación de OT). Sin motores ni tablas nuevas.
"""

import datetime as _dt

import pytest

pytestmark = pytest.mark.db

EMP = "T-GMAO-1"
REP = "GMAO_REP1"


@pytest.fixture()
def seed(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM movimientos_stock WHERE id_empresa=%s AND codigo_articulo=%s", (EMP, REP))
            cur.execute("DELETE FROM ot_recursos WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM costes_ot WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM ordenes_trabajo WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM planes_mantenimiento WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM activos WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM articulos WHERE id_empresa=%s AND codigo=%s", (EMP, REP))
            c.commit()
    _b()
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, Stock_tienda) "
                    "VALUES (%s,%s,%s,%s,%s)", (REP, EMP, "Repuesto", 5.0, 100))
        c.commit()
    yield
    _b()


def _mov(db, id_doc, tipo):
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM movimientos_stock WHERE id_empresa=%s AND id_documento=%s "
                    "AND tipo_movimiento=%s", (EMP, id_doc, tipo))
        r = cur.fetchone()
        return (r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0


def test_ciclo_correctivo_con_repuesto(seed, db):
    from src.services.gmao import activos, ordenes

    aid = activos.crear_activo("GM_A1", "Máquina de prueba", tipo="maquinaria",
                               criticidad="alta", id_empresa=EMP)
    assert aid

    oid = ordenes.crear_ot(tipo="correctiva", id_activo=aid, descripcion="Avería motor", id_empresa=EMP)
    assert oid and ordenes.obtener(oid)["estado"] == "borrador"

    # borrador → abierta → asignada → en_curso.
    assert ordenes.cambiar_estado(oid, "abierta", id_empresa=EMP)["ok"]
    assert ordenes.asignar(oid, 1, id_empresa=EMP)["ok"]         # técnico id=1 (INT)
    assert ordenes.iniciar(oid, id_empresa=EMP)["ok"]
    assert ordenes.obtener(oid)["estado"] == "en_curso"

    # repuesto + finalización (consume por kárdex oficial + costes).
    rid = ordenes.añadir_repuesto(oid, REP, 3, coste_unitario=5, id_empresa=EMP)
    assert rid
    r = ordenes.finalizar(oid, horas_mano_obra=2, id_empresa=EMP, usuario=1)
    assert r["ok"]
    assert ordenes.obtener(oid)["estado"] == "finalizada"
    assert _mov(db, f"OT:{oid}", "SALIDA_PRODUCCION") >= 1     # repuesto consumido por el kárdex OFICIAL

    # transición inválida rechazada sin romper (finalizada → en_curso no permitido).
    assert ordenes.iniciar(oid, id_empresa=EMP)["ok"] is False


def test_preventivo_genera_ot(seed):
    from src.services.gmao import activos, ordenes, planes
    aid = activos.crear_activo("GM_A2", "Compresor", id_empresa=EMP)
    ayer = _dt.date.today() - _dt.timedelta(days=1)
    pid = planes.crear_plan("PLAN1", "Engrase mensual", id_activo=aid, frecuencia="mensual",
                            proxima_fecha=ayer, id_empresa=EMP)
    assert pid
    generadas = planes.generar_ot_preventivas(id_empresa=EMP)
    assert len(generadas) >= 1
    # las OT preventivas nacen en estado "abierta" y aparecen en el listado que consume la GUI.
    prev = [o for o in ordenes.listar(id_empresa=EMP) if o.get("tipo") == "preventiva"]
    assert len(prev) >= 1
