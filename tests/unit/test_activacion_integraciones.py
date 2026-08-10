"""
Readiness de integraciones de producción (R2/R3/R4): el readout `activacion` reporta el estado real
(simulado/live) sin cobrar/conectar/activar nada. Por defecto (sin credenciales) todo está 'preparado'
(simulado) — honestidad: nunca se marca 'live' lo que no lo está.
"""

import pytest

pytestmark = pytest.mark.db

from src.services.integraciones import activacion as A


def test_estado_lista_las_tres_integraciones():
    est = A.estado_activacion(id_empresa="ACT-TEST-EMP")
    claves = {e["clave"] for e in est}
    assert claves == {"pagos", "banca_psd2", "aeat"}
    for e in est:
        assert e["requisito"] in ("R2", "R3", "R4")
        assert e["modo"] in ("live", "simulado")
        assert e["listo"] == (e["modo"] == "live")
        assert isinstance(e["requiere"], list) and e["requiere"]      # qué falta para activar


def test_sin_credenciales_todo_preparado_no_live():
    # Empresa sin conexiones/certificados → todas en 'simulado' (base lista, no activada).
    est = A.estado_activacion(id_empresa="ACT-TEST-EMP-VACIA")
    assert all(e["modo"] == "simulado" and e["listo"] is False for e in est)


def test_resumen_coherente():
    r = A.resumen(id_empresa="ACT-TEST-EMP-VACIA")
    assert r["total"] == 3
    assert r["en_produccion"] == [] and set(r["preparadas"]) == {"pagos", "banca_psd2", "aeat"}
    assert r["todo_en_produccion"] is False
    assert len(r["detalle"]) == 3
