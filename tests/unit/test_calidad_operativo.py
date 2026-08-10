"""
Tests · Calidad OPERATIVA (cierre de brecha funcional).

Verifica el ciclo real que ahora expone la GUI operativa, ejecutando los servicios existentes:
inspección de RECEPCIÓN rechazada → NC abierta AUTOMÁTICAMENTE (integración Compras→Calidad) →
ciclo de NC (abierta→en_análisis→accionada→cerrada) → acción CAPA ligada a la NC
(abierta→en_curso→cerrada con eficacia). Comprueba también que las transiciones inválidas se rechazan
sin romper. Sin motores ni tablas nuevas.
"""

import pytest

pytestmark = pytest.mark.db

EMP = "T-CAL-1"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM acciones_correctivas WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM no_conformidades WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM inspecciones WHERE id_empresa=%s", (EMP,))
            c.commit()
    _b()
    yield
    _b()


def test_recepcion_rechazo_genera_nc_y_capa(limpia):
    from src.services.calidad import capa, inspecciones, no_conformidades

    # 1) Inspección de recepción RECHAZADA → NC automática (Compras→Calidad).
    r = inspecciones.registrar_inspeccion(
        fase="recepcion", articulo="CAL_ART", cantidad_inspeccionada=100, cantidad_rechazada=12,
        resultado="rechazada", inspector=None, id_empresa=EMP)
    assert r["ok"] and r["inspeccion"]
    nc = r["no_conformidad"]
    assert nc, "una recepción rechazada debe abrir una NC automáticamente"
    assert no_conformidades.obtener(nc)["estado"] == "abierta"

    # 2) Ciclo de NC: abierta → en_análisis → accionada → cerrada.
    assert no_conformidades.cambiar_estado(nc, "en_analisis", id_empresa=EMP)["ok"]
    # transición inválida (en_análisis → abierta) rechazada sin romper.
    assert no_conformidades.cambiar_estado(nc, "abierta", id_empresa=EMP)["ok"] is False
    assert no_conformidades.cambiar_estado(nc, "accionada", id_empresa=EMP)["ok"]

    # 3) Acción CAPA ligada a la NC: abierta → en_curso → cerrada (con eficacia).
    cid = capa.crear_accion("Revisar proveedor y reinspección", tipo="correctiva", id_nc=nc,
                            responsable=None, id_empresa=EMP)
    assert cid
    assert capa.cambiar_estado(cid, "en_curso", id_empresa=EMP)["ok"]
    assert capa.cambiar_estado(cid, "cerrada", eficacia="eficaz", id_empresa=EMP)["ok"]

    # 4) Cierre de la NC.
    assert no_conformidades.cambiar_estado(nc, "cerrada", id_empresa=EMP)["ok"]
    assert no_conformidades.obtener(nc)["estado"] == "cerrada"

    # 5) Aparecen en los listados que consume la GUI.
    assert any(x["id"] == nc for x in no_conformidades.listar(id_empresa=EMP))
    assert any(x["id"] == cid for x in capa.listar(id_empresa=EMP))


def test_inspeccion_aceptada_no_genera_nc(limpia):
    from src.services.calidad import inspecciones, no_conformidades
    r = inspecciones.registrar_inspeccion(fase="recepcion", articulo="CAL_OK",
                                          cantidad_inspeccionada=50, cantidad_rechazada=0,
                                          resultado="aceptada", id_empresa=EMP)
    assert r["ok"] and r["no_conformidad"] is None
    assert no_conformidades.listar(id_empresa=EMP) == []
