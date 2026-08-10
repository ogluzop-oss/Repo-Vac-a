"""
Fase 4b: orquestación multi-terminal. Exactamente UNA terminal graba cada cámara (concesiones/leases con
UNIQUE por cámara), con failover al caducar y cesión al parar. Reparto real entre dos RecorderService.
"""

import os
import shutil
import time

import pytest

from src.services.camaras import grabacion as G
from src.services.camaras import orquestacion as O
from src.services.camaras import registro as R


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _limpiar(fab, emp, *cids):
    fab.al_limpiar(lambda: shutil.rmtree(os.path.join(G._base_grabaciones(), str(emp)), ignore_errors=True))
    for cid in cids:
        fab._borrar("camaras", "id", cid)
        fab._borrar("camaras_grabador", "id_camara", cid)
        fab._borrar("camaras_grabaciones", "id_camara", cid)


def test_una_sola_terminal_reclama_la_camara(fab, emp):
    cid = R.crear_camara("C", id_empresa=emp, id_centro="CT", fuente="badsource://x")
    _limpiar(fab, emp, cid)
    assert O.reclamar(cid, terminal="T1", id_empresa=emp) is True     # libre → T1 la toma
    assert O.reclamar(cid, terminal="T2", id_empresa=emp) is False    # ocupada y vigente → T2 no
    assert O.propietario(cid) == "T1"
    assert O.reclamar(cid, terminal="T1", id_empresa=emp) is True     # T1 renueva la suya


def test_failover_al_caducar_la_concesion(fab, emp):
    cid = R.crear_camara("C", id_empresa=emp, id_centro="CT", fuente="badsource://x")
    _limpiar(fab, emp, cid)
    assert O.reclamar(cid, terminal="T1", id_empresa=emp, ttl_seg=-5) is True   # nace ya caducada
    assert O.propietario(cid) is None                                          # caducada → libre
    assert O.reclamar(cid, terminal="T2", id_empresa=emp) is True              # otra terminal la toma
    assert O.propietario(cid) == "T2"


def test_liberar_cede_la_concesion(fab, emp):
    cid = R.crear_camara("C", id_empresa=emp, id_centro="CT", fuente="badsource://x")
    _limpiar(fab, emp, cid)
    O.reclamar(cid, terminal="T1", id_empresa=emp)
    assert O.liberar(terminal="T1", id_empresa=emp) >= 1
    assert O.propietario(cid) is None
    assert O.reclamar(cid, terminal="T2", id_empresa=emp) is True


def test_dos_recorders_no_graban_la_misma_camara(fab, emp):
    c1 = R.crear_camara("C1", id_empresa=emp, id_centro="CT", fuente="badsource://1")
    c2 = R.crear_camara("C2", id_empresa=emp, id_centro="CT", fuente="badsource://2")
    _limpiar(fab, emp, c1, c2)
    svcA = G.RecorderService(terminal="A")
    svcB = G.RecorderService(terminal="B")
    try:
        nA = svcA.arrancar_departamento(emp, "CT")           # A llega primero → reclama las libres
        nB = svcB.arrancar_departamento(emp, "CT")           # B no puede tomar las ya ocupadas
        assert nA == 2 and nB == 0
        assert svcA.activas() == 2 and svcB.activas() == 0   # ninguna cámara grabada por dos
        # FAILOVER: A cae (cede concesiones) → B las reclama en su latido
        svcA.detener()
        assert svcB.renovar() == 2
        assert svcB.activas() == 2
        assert {O.propietario(c1), O.propietario(c2)} == {"B"}
    finally:
        svcA.detener()
        svcB.detener()
        time.sleep(0.2)
