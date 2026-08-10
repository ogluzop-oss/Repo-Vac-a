"""
Tests · Detección de la wake word de SOMA (`utils.soma_worker.detectar_wake`).

Fija el equilibrio PRECISIÓN/COBERTURA tras el endurecimiento anti-falsos-positivos:
  · Frases de conversación normal (prefijo común + palabra española homófona de "SOMA": toma/coma/
    roma/goma/sola/sopa/sonia...) NO deben activar a SOMA.
  · Las wakes reales ("Ey SOMA", "SOMA", y las mal-transcripciones plausibles que empiezan por /s/)
    SÍ deben activar.

Es tuning sensible: si alguien vuelve a añadir homófonos comunes al set laxo o baja el umbral difuso,
estos tests lo detectan.
"""

import pytest

from src.utils.soma_worker import detectar_wake

# Habla normal que NO debe despertar a SOMA (causaban falsos positivos antes del fix).
FALSOS = [
    "oye toma esto", "vale coma tranquilo", "a solas", "ok roma", "dame la goma",
    "es una broma", "hola sonia", "toma nota", "la sopa está lista", "eso sí",
    "ah sí claro", "eh sá", "que sona bien", "e sopa", "ok comamos", "oye ramona",
    "vale roma antigua", "hola toma asiento",
]

# Wakes reales que SÍ deben activar (incluye mal-oídos plausibles con onset /s/ y multiidioma).
REALES = [
    "ey soma", "oye soma", "soma abre ventas", "hey soma", "ey zona abre tpv",
    "soma", "e soma", "el soma abre caja", "soma cierra", "hey samma",
    "oye somo", "ey sama abre caja",
]


@pytest.mark.parametrize("frase", FALSOS)
def test_no_activa_en_habla_normal(frase):
    found, _ = detectar_wake(frase)
    assert found is False, f"FALSO POSITIVO: {frase!r} activó la wake word"


@pytest.mark.parametrize("frase", REALES)
def test_activa_con_wake_real(frase):
    found, _ = detectar_wake(frase)
    assert found is True, f"WAKE PERDIDA: {frase!r} no activó a SOMA"


def test_comando_inline_se_extrae():
    found, cmd = detectar_wake("soma abre ventas")
    assert found and cmd == "ABRE VENTAS"
    found, cmd = detectar_wake("ey soma")   # wake a secas → sin comando en línea
    assert found and cmd == ""
