"""
IA empresarial — dominios nuevos: PRODUCCIÓN (recomienda fabricar según demanda vs stock, explosiona BOM) y
DOCUMENTAL (clasifica/duplicados del centro documental). Honestidad: motor heurístico ETIQUETADO, sin mocks.
"""

import pytest

from src.db import documentos as DOC
from src.services.ia import documental as D
from src.services.mrp import bom
from src.services.prediccion import produccion as P


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


# ── IA de producción ──────────────────────────────────────────────────────────
def test_produccion_recomienda_fabricar_con_componentes(emp, fab, monkeypatch):
    bid = bom.crear_bom("IAP-FAB", lineas=[{"componente": "IAP-COMP", "cantidad": 2}], id_empresa=emp)
    fab.al_limpiar(lambda: (fab._borrar("bom_lineas", "id_bom", bid), fab._borrar("bom", "id", bid)))
    # demanda proxy: 50 uds/30d del producto terminado (stock 0 → sugerido 50)
    monkeypatch.setattr("src.services.prediccion.adaptadores.rotacion_articulos",
                        lambda id_empresa=None: [{"codigo": "IAP-FAB", "uds": 50}])
    r = P.predecir(emp)
    assert r["activo"] and r["dominio"] == "produccion"
    rec = [x for x in r["recomendaciones"] if x["entidad_id"] == "IAP-FAB"]
    assert rec and rec[0]["accion"] == "fabricar" and rec[0]["cantidad_sugerida"] == 50
    # el componente falta (necesita 2×50=100, stock 0) → prioridad ALTA
    assert any(c["componente"] == "IAP-COMP" and c["necesario"] == 100
               for c in rec[0]["componentes_faltantes"])
    assert rec[0]["prioridad"] == "ALTA" and rec[0]["workflow"] == "mrp_orden"
    # HONESTIDAD: el motor se etiqueta como heurístico (no finge ML)
    assert r["motor"]["tipo"] == "heuristica" and r["motor"]["es_ml"] is False


def test_produccion_desactivable(emp):
    from src.services.prediccion import configuracion as C
    C.configurar(emp, produccion=False)
    try:
        assert P.predecir(emp)["activo"] is False
    finally:
        C.configurar(emp, produccion=True)


# ── IA documental ─────────────────────────────────────────────────────────────
def test_documental_detecta_duplicados(emp, fab, tmp_path):
    contenido = b"IA-DOC-CONTENIDO-UNICO-98765"
    f1 = tmp_path / "iadoc1.pdf"; f1.write_bytes(contenido)
    f2 = tmp_path / "iadoc2.pdf"; f2.write_bytes(contenido)   # mismo contenido → mismo hash
    fab.al_limpiar(lambda: [fab._borrar("documentos_registro", "nombre", n)
                            for n in ("iadoc1.pdf", "iadoc2.pdf")])
    DOC.registrar_documento(str(f1), tipo="otros", id_empresa=emp)
    DOC.registrar_documento(str(f2), tipo="otros", id_empresa=emp)
    res = D.analizar(emp)
    assert res["activo"] and res["dominio"] == "documental"
    grupos = [g for g in res["duplicados"]
              if {"iadoc1.pdf", "iadoc2.pdf"} <= set(g["documentos"])]
    assert grupos and len(grupos[0]["documentos"]) >= 2       # detecta el par duplicado
    assert any("duplicad" in s.lower() for s in res["sugerencias"])
    assert res["motor"]["tipo"] == "heuristica"               # honesto


# ── Fachada central ───────────────────────────────────────────────────────────
def test_fachada_incluye_nuevos_dominios(emp):
    from src.services.prediccion.motor import PredictionService
    svc = PredictionService()
    assert svc.produccion(emp)["dominio"] == "produccion"
    assert svc.documental(emp)["dominio"] == "documental"
    # los nuevos dominios agregan sus alertas al motor central sin romper
    assert isinstance(svc.alertas(emp), list)
