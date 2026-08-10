"""
Estado global de la cuenta (`services/cuenta.resumen`): agrega ítems core (datos empresa/edición/
asistente/plan) en un % de configuración + integraciones de producción aparte (opcionales). Best-effort:
no rompe aunque falten fuentes.
"""

import pytest

pytestmark = pytest.mark.db

from src.services import cuenta as C


def test_resumen_estructura_y_porcentaje():
    r = C.resumen(id_empresa="CUENTA-TEST-EMP")
    # estructura
    for k in ("porcentaje", "completado", "items", "pendientes", "integraciones", "total", "hechos"):
        assert k in r
    claves = {it["clave"] for it in r["items"]}
    assert claves == {"datos_empresa", "edicion", "asistente", "plan"}
    # porcentaje coherente con hechos/total
    assert 0 <= r["porcentaje"] <= 100
    assert r["porcentaje"] == int(round(100 * r["hechos"] / r["total"]))
    assert r["completado"] == (r["porcentaje"] >= 100)
    # los pendientes son exactamente los ítems no hechos
    assert set(r["pendientes"]) == {it["titulo"] for it in r["items"] if not it["hecho"]}


def test_integraciones_no_penalizan_el_porcentaje():
    # Las integraciones de producción se listan aparte (activacion) y no cuentan en el % core.
    r = C.resumen(id_empresa="CUENTA-TEST-EMP")
    assert r["integraciones"]["total"] == 3          # pagos / banca_psd2 / aeat
    assert r["total"] == 4                            # solo los 4 ítems core cuentan


def test_cada_item_tiene_accion_legible():
    r = C.resumen(id_empresa="CUENTA-TEST-EMP")
    for it in r["items"]:
        assert it.get("titulo") and it.get("accion") and "detalle" in it
        assert isinstance(it["hecho"], bool)
