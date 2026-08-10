"""
Fase 2: mapeo asistido por IA DEGRADABLE. Sin backend (sin API) cae a la heurística; con un backend inyectado
manda la IA; ante respuesta no-JSON degrada sin romper. No llama a ninguna API real.
"""

import pytest

from src.services.importacion import mapeo as heur
from src.services.importacion import mapeo_ia


@pytest.fixture(autouse=True)
def _reset_backend():
    yield
    mapeo_ia._backend = None
    mapeo_ia._intentado = False


def test_sin_backend_cae_a_heuristica(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    mapeo_ia._backend = None
    mapeo_ia._intentado = False
    cols = ["codigo", "nombre", "pvp"]
    assert mapeo_ia.sugerir_mapeo_ia(cols) == heur.sugerir_mapeo(cols)
    assert mapeo_ia.disponible() is False


def test_backend_inyectado_manda_sobre_heuristica():
    cols = ["clave_producto", "titulo", "precio"]                 # 'clave_producto' no lo pilla la heurística
    mapeo_ia.set_backend(lambda sp, ut: '{"codigo":"clave_producto","nombre":"titulo"}')
    m = mapeo_ia.sugerir_mapeo_ia(cols)
    assert m["codigo"] == "clave_producto" and m["nombre"] == "titulo"
    assert mapeo_ia.disponible() is True


def test_respuesta_no_json_degrada_a_heuristica():
    cols = ["codigo", "nombre", "precio"]
    mapeo_ia.set_backend(lambda sp, ut: "lo siento, no puedo")
    assert mapeo_ia.sugerir_mapeo_ia(cols) == heur.sugerir_mapeo(cols)


def test_ia_ignora_columnas_inexistentes():
    cols = ["codigo", "nombre"]
    mapeo_ia.set_backend(lambda sp, ut: '{"codigo":"codigo","precio":"columna_que_no_existe"}')
    m = mapeo_ia.sugerir_mapeo_ia(cols)
    assert m["codigo"] == "codigo" and "precio" not in m           # columna inválida descartada
