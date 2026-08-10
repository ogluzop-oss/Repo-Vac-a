"""
Ecosistema SaaS — cierre: facturación automática de suscripciones vencidas (reutiliza suscripciones.renovar +
BillingProvider simulado) y marketplaces de primer nivel (IA/plantillas/conectores) sobre el App Store existente.
"""

import datetime as dt

import pytest

import importlib

from src.services.saas import facturacion_automatica as FA

MK = importlib.import_module("src.services.marketplace.catalogo")   # el paquete re-exporta 'catalogo' (función)


@pytest.fixture
def emp2(fab):
    e = fab.empresa("SAAS FACTURACION")

    def _limpiar():
        for t in ("pagos_saas", "facturas_saas", "suscripciones", "empresa_licencia"):
            fab._borrar(t, "id_empresa", e)
    fab.al_limpiar(_limpiar)
    return e


def _crear_suscripcion_vencida(db, emp, dias_vencida=1):
    ayer = dt.date.today() - dt.timedelta(days=dias_vencida)
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO suscripciones (id_empresa, codigo_plan, ciclo, estado, proveedor_pago, "
                    "fecha_inicio, proximo_cobro) VALUES (%s,'BASIC','mensual','activa','simulado',%s,%s)",
                    (emp, ayer, ayer))
        c.commit()


def _n_facturas(db, emp):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM facturas_saas WHERE id_empresa=%s", (emp,))
        return cur.fetchone()[0]


def test_facturar_vencidas_emite_factura(emp2, db):
    _crear_suscripcion_vencida(db, emp2)
    assert emp2 in FA.suscripciones_vencidas()               # detectada como vencida
    assert _n_facturas(db, emp2) == 0
    res = FA.facturar_vencidas()
    assert res["procesadas"] >= 1
    assert _n_facturas(db, emp2) == 1                          # factura emitida automáticamente
    # tras renovar, el próximo cobro se movió al futuro → ya no está vencida
    assert emp2 not in FA.suscripciones_vencidas()


def test_facturar_vencidas_idempotente(emp2, db):
    _crear_suscripcion_vencida(db, emp2)
    FA.facturar_vencidas()
    FA.facturar_vencidas()                                    # segunda pasada el mismo día
    assert _n_facturas(db, emp2) == 1                          # NO vuelve a facturar (proximo_cobro futuro)


def test_job_scheduler_registrado():
    from src.services import scheduler_registry
    assert "saas_facturacion" in scheduler_registry.CATALOGO


# ── Marketplaces IA / plantillas / conectores (categorías del App Store) ──────
def test_marketplaces_estandar_existen(emp2):
    cats = set(MK.categorias(emp2))
    assert {"ia", "plantilla", "conector", "extension"} <= cats     # secciones siempre presentes
    # los marketplaces con nombre equivalen a filtrar el catálogo por categoría
    assert MK.catalogo_ia(emp2) == MK.catalogo(emp2, categoria="ia")
    assert MK.catalogo_plantillas(emp2) == MK.catalogo(emp2, categoria="plantilla")
    assert isinstance(MK.catalogo_conectores(emp2), list)
