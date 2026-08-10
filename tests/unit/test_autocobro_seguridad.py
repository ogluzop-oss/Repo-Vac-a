"""
Tests · Autocobro · Capa 3 (auditoría de seguridad de la caja al ERP).

Verifica la captura de metadatos de seguridad por venta (security_logs) e incidencias por artículo, y
las consultas de analítica (artículos conflictivos = señal de merma/packaging; resumen agregado).
"""

import pytest

from src.services.tpv import autocobro_seguridad as SEC

pytestmark = pytest.mark.db

EMP = "T-SECLOG"
TIE = "T-SECLOG-1"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM autocobro_incidencias WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM autocobro_seguridad_log WHERE id_empresa=%s", (EMP,))
            c.commit()
    _b()
    yield
    _b()


def test_incidencias_y_articulos_conflictivos(limpia):
    # "El 80% se bloquea al comprar estas galletas" → señal de packaging cambiado.
    SEC.registrar_incidencia("SCO-04", "GALLETAS-X", "Galletas", SEC.TIPO_BLOQUEO_PESO,
                             id_empresa=EMP, id_tienda=TIE)
    SEC.registrar_incidencia("SCO-04", "GALLETAS-X", "Galletas", SEC.TIPO_BLOQUEO_PESO,
                             id_empresa=EMP, id_tienda=TIE)
    SEC.registrar_incidencia("SCO-04", "QUESO-Y", "Queso", SEC.TIPO_ANULACION,
                             id_empresa=EMP, id_tienda=TIE)
    top = SEC.articulos_conflictivos(id_empresa=EMP, dias=1)
    assert top and top[0]["codigo"] == "GALLETAS-X" and top[0]["incidencias"] == 2
    # Filtrado por tipo.
    solo_anul = SEC.articulos_conflictivos(id_empresa=EMP, dias=1, tipo=SEC.TIPO_ANULACION)
    assert {r["codigo"] for r in solo_anul} == {"QUESO-Y"}


def test_resumen_de_ventas_seguridad(limpia):
    SEC.registrar_venta_seguridad("SCO-04", 111, intervenciones=2, anulaciones=1,
                                  autorizado_por="EMP-402", duracion_seg=124, items=5, total=23.9,
                                  id_empresa=EMP, id_tienda=TIE)
    SEC.registrar_venta_seguridad("SCO-04", 112, intervenciones=0, anulaciones=0,
                                  autorizado_por=None, duracion_seg=40, items=3, total=9.9,
                                  id_empresa=EMP, id_tienda=TIE)
    r = SEC.resumen(id_empresa=EMP, dias=1)
    assert r["ventas"] == 2
    assert r["intervenciones_peso"] == 2
    assert r["anulaciones"] == 1
    assert r["ventas_con_intervencion"] == 1
    assert r["duracion_media_seg"] == 82.0


def test_degradable_sin_tenant(limpia):
    # No debe lanzar aunque falte tenant explícito (usa el actual o None).
    assert SEC.registrar_incidencia("SCO-09", "A", "Art", id_empresa=EMP, id_tienda=TIE) is True
    assert isinstance(SEC.resumen(id_empresa=EMP), dict)
