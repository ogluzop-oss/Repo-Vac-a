"""
MRP — BOM (simple/multinivel), explosion, centros/rutas, planificador (necesidades/sugerencias),
costes estandar, analitica/IA. (El flujo de OF + kardex se prueba en test_fabricacion.py.)
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
        for t in ("bom_lineas", "bom", "operaciones_fabricacion", "rutas_fabricacion",
                  "capacidades_prod", "centros_trabajo_prod", "mrp_sugerencias", "costes_fabricacion"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (E,))
        conn.commit()


def test_bom_simple_y_explosion(db, limpia):
    from src.services.mrp import bom
    P, A, B = (f"P_{uuid.uuid4().hex[:5]}", f"A_{uuid.uuid4().hex[:5]}", f"B_{uuid.uuid4().hex[:5]}")
    _art(db, P, A, B)
    bid = bom.crear_bom(P, lineas=[{"componente": A, "cantidad": 2}, {"componente": B, "cantidad": 3}], id_empresa=E)
    assert bid
    exp = {x["componente"]: x["cantidad"] for x in bom.explosionar(P, 10, id_empresa=E)}
    assert exp[A] == 20 and exp[B] == 30


def test_bom_multinivel(db, limpia):
    from src.services.mrp import bom
    P, SUB, RAW = (f"P_{uuid.uuid4().hex[:5]}", f"S_{uuid.uuid4().hex[:5]}", f"R_{uuid.uuid4().hex[:5]}")
    _art(db, P, SUB, RAW)
    bom.crear_bom(SUB, lineas=[{"componente": RAW, "cantidad": 4}], id_empresa=E)
    bom.crear_bom(P, lineas=[{"componente": SUB, "cantidad": 2}], id_empresa=E)
    comps = bom.explosionar(P, 5, id_empresa=E)
    raw = next(c for c in comps if c["componente"] == RAW)
    sub = next(c for c in comps if c["componente"] == SUB)
    assert sub["fabricado"] is True and raw["fabricado"] is False
    assert raw["cantidad"] == 40   # 5 * 2 * 4


def test_centros_y_rutas(db, limpia):
    from src.services.mrp import centros
    cid = centros.crear_centro(f"CT_{uuid.uuid4().hex[:4]}", "Linea", tipo="linea", coste_hora=30,
                               unidades_hora=10, id_empresa=E)
    assert cid and centros.capacidad_diaria(cid) == 80   # 8h * 10u
    art = f"P_{uuid.uuid4().hex[:5]}"; _art(db, art)
    rid = centros.crear_ruta(art, f"RT_{uuid.uuid4().hex[:4]}",
                             operaciones=[{"nombre": "Op1", "id_centro": cid, "tiempo_estandar_min": 6}], id_empresa=E)
    assert rid and len(centros.operaciones_ruta(rid)) == 1


def test_planificador_sugerencias(db, limpia):
    from src.services.mrp import bom, planificador
    P, A = (f"P_{uuid.uuid4().hex[:5]}", f"A_{uuid.uuid4().hex[:5]}")
    _art(db, P, A)
    bom.crear_bom(P, lineas=[{"componente": A, "cantidad": 2}], id_empresa=E)
    r = planificador.generar_sugerencias({P: 10}, persistir=True, id_empresa=E)
    assert any(s["articulo"] == A for s in r["compras"])     # A es hoja -> compra
    assert any(s["articulo"] == P for s in r["fabricacion"]) # P -> fabricacion
    assert planificador.listar_sugerencias(id_empresa=E)


def test_costes_estandar(db, limpia):
    from src.services.mrp import bom, centros, costes
    P, A = (f"P_{uuid.uuid4().hex[:5]}", f"A_{uuid.uuid4().hex[:5]}")
    _art(db, P, A)
    bom.crear_bom(P, lineas=[{"componente": A, "cantidad": 2}], id_empresa=E)
    cid = centros.crear_centro(f"CT_{uuid.uuid4().hex[:4]}", "L", coste_hora=60, id_empresa=E)
    centros.crear_ruta(P, f"RT_{uuid.uuid4().hex[:4]}",
                       operaciones=[{"nombre": "Op", "id_centro": cid, "tiempo_estandar_min": 30}], id_empresa=E)
    c = costes.coste_estimado_articulo(P, id_empresa=E)
    assert c["mano_obra"] == 30.0   # 0.5h * 60
    assert "total" in c and c["total"] > 0


def test_analitica_simulacion(db, limpia):
    from src.services.mrp import analitica, centros
    cid = centros.crear_centro(f"CT_{uuid.uuid4().hex[:4]}", "L", unidades_hora=10, id_empresa=E)
    sim = analitica.simulacion_capacidad(cid, 200, id_empresa=E)
    assert sim["ok"] and sim["dias_necesarios"] == 3   # 200 / 80 -> 3 dias
    assert "of_total" in analitica.kpis(id_empresa=E)
