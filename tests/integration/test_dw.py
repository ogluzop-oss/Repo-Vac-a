"""
BI Corporativo — Data Warehouse + ETL: poblado idempotente desde calculadores/analiticas,
consulta y log de ETL.
"""

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID

E = EMPRESA_DEFAULT_ID


def test_guardar_hecho_idempotente(db):
    from src.services.bi_corp import dw
    ok = dw.guardar_hecho("ventas", "facturacion", 1000, granularidad="mensual", periodo="2099-01",
                          fecha="2099-01-31", id_empresa=E)
    assert ok
    # segunda escritura misma clave -> actualiza, no duplica
    dw.guardar_hecho("ventas", "facturacion", 2000, granularidad="mensual", periodo="2099-01",
                     fecha="2099-01-31", id_empresa=E)
    filas = dw.consultar(dominio="ventas", metrica="facturacion", periodo="2099-01", id_empresa=E)
    assert len(filas) == 1 and float(filas[0]["valor"]) == 2000.0
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM dw_hechos WHERE periodo='2099-01' AND id_empresa=%s", (E,))
        conn.commit()


def test_etl_pobla_multidominio(db):
    from src.services.bi_corp import dw
    r = dw.ejecutar_etl(granularidad="mensual", id_empresa=E)
    assert r["filas"] >= 1
    assert "ventas" in r["detalle"]
    # log de ETL registrado
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM dw_etl_ejecuciones WHERE id_empresa=%s", (E,))
        n = cur.fetchone()
        assert (n[0] if not isinstance(n, dict) else list(n.values())[0]) >= 1


def test_etl_granularidades(db):
    from src.services.bi_corp import dw
    for g in ("diaria", "semanal", "mensual", "anual"):
        r = dw.ejecutar_etl(dominios=["ventas"], granularidad=g, id_empresa=E)
        assert r["granularidad"] == g
