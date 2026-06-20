"""
F4.6 · Parametrización legal del motor de nómina — carga robusta y validación.

Tests puros (sin Qt/BD): carga de año válido, año inexistente (fallback), JSON corrupto,
claves/contingencias/bases/grupos ausentes, tipos incorrectos, topes por grupo,
multi-ejercicio y presencia del recurso en el árbol de assets (empaquetado).
"""

import json
import os

import pytest

from src.rrhh.nomina_motor import ParametrosAnio
from src.rrhh.parametros_cotizacion import (ParametrosCotizacionError, _validar,
                                           cargar_parametros)

_EJ_OK = {
    "ss_trabajador": {"comunes": 4.7, "fp": 0.1, "mei": 0.13, "horas_extra": 4.7},
    "ss_empresa": {"comunes": 23.6, "fp": 0.6, "fogasa": 0.2, "at_ep": 1.5, "mei": 0.67, "horas_extra": 23.6},
    "desempleo_trabajador": {"indefinido": 1.55, "temporal": 1.6},
    "desempleo_empresa": {"indefinido": 5.5, "temporal": 6.7},
    "bases": {"tope_max_mensual": 4909.5, "tope_min_mensual": 1323.0},
    "grupos": {"1": {"min": 1847.4, "max": 4909.5}, "7": {"min": 1323.0, "max": 4909.5}},
    "irpf": {"modo": "tipo_fijo", "tipo_defecto": 15.0},
}


def _escribir(tmp_path, contenido, pais="es", monkeypatch=None):
    ruta = tmp_path / f"cotizacion_{pais}.json"
    if isinstance(contenido, str):
        ruta.write_text(contenido, encoding="utf-8")
    else:
        ruta.write_text(json.dumps(contenido), encoding="utf-8")
    if monkeypatch is not None:
        monkeypatch.setattr("src.rrhh.parametros_cotizacion._ruta", lambda pais: str(ruta))
    return str(ruta)


# ── Carga real del recurso empaquetado ────────────────────────────────────────
def test_recurso_existe_en_assets():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert os.path.exists(os.path.join(root, "assets", "rrhh", "cotizacion_es.json"))


def test_carga_anio_valido_2025_y_2026():
    p25 = cargar_parametros(2025)
    p26 = cargar_parametros(2026)
    assert isinstance(p25, ParametrosAnio) and p25.anio == 2025
    assert p26.anio == 2026
    assert p25.ss_trabajador["comunes"] == 4.70
    assert p26.ss_trabajador["mei"] == 0.15        # MEI sube en 2026


def test_anio_inexistente_usa_ultimo():
    p = cargar_parametros(2099)                     # no existe → último disponible
    assert p.anio in (2025, 2026)


def test_topes_por_grupo():
    p = cargar_parametros(2026)
    low1, high1 = p.limites_grupo("1")
    low7, _ = p.limites_grupo("7")
    assert low1 == 1847.40 and high1 == 4909.50
    assert low7 == 1323.00


# ── Carga robusta ──────────────────────────────────────────────────────────────
def test_fichero_ausente(monkeypatch, tmp_path):
    monkeypatch.setattr("src.rrhh.parametros_cotizacion._ruta",
                        lambda pais: str(tmp_path / "no_existe.json"))
    with pytest.raises(ParametrosCotizacionError, match="no encontrado"):
        cargar_parametros(2026)


def test_json_corrupto(monkeypatch, tmp_path):
    _escribir(tmp_path, "{ esto no es json válido", monkeypatch=monkeypatch)
    with pytest.raises(ParametrosCotizacionError, match="corrupto"):
        cargar_parametros(2026)


def test_sin_ejercicios(monkeypatch, tmp_path):
    _escribir(tmp_path, {"_meta": {"x": 1}}, monkeypatch=monkeypatch)
    with pytest.raises(ParametrosCotizacionError, match="Sin ejercicios"):
        cargar_parametros(2026)


# ── Validación de integridad ───────────────────────────────────────────────────
def test_falta_bloque_contingencia(monkeypatch, tmp_path):
    ej = json.loads(json.dumps(_EJ_OK)); del ej["ss_empresa"]
    _escribir(tmp_path, {"2026": ej}, monkeypatch=monkeypatch)
    with pytest.raises(ParametrosCotizacionError, match="ss_empresa"):
        cargar_parametros(2026)


def test_falta_contingencia_concreta(monkeypatch, tmp_path):
    ej = json.loads(json.dumps(_EJ_OK)); del ej["ss_trabajador"]["mei"]
    _escribir(tmp_path, {"2026": ej}, monkeypatch=monkeypatch)
    with pytest.raises(ParametrosCotizacionError, match="mei"):
        cargar_parametros(2026)


def test_falta_base(monkeypatch, tmp_path):
    ej = json.loads(json.dumps(_EJ_OK)); del ej["bases"]["tope_max_mensual"]
    _escribir(tmp_path, {"2026": ej}, monkeypatch=monkeypatch)
    with pytest.raises(ParametrosCotizacionError, match="tope_max_mensual"):
        cargar_parametros(2026)


def test_grupos_vacios(monkeypatch, tmp_path):
    ej = json.loads(json.dumps(_EJ_OK)); ej["grupos"] = {}
    _escribir(tmp_path, {"2026": ej}, monkeypatch=monkeypatch)
    with pytest.raises(ParametrosCotizacionError, match="grupos"):
        cargar_parametros(2026)


def test_grupo_sin_min_max(monkeypatch, tmp_path):
    ej = json.loads(json.dumps(_EJ_OK)); ej["grupos"]["1"] = {"min": 1000.0}
    _escribir(tmp_path, {"2026": ej}, monkeypatch=monkeypatch)
    with pytest.raises(ParametrosCotizacionError, match="min/max"):
        cargar_parametros(2026)


def test_tipo_incorrecto(monkeypatch, tmp_path):
    ej = json.loads(json.dumps(_EJ_OK)); ej["ss_trabajador"]["comunes"] = "cuatro"
    _escribir(tmp_path, {"2026": ej}, monkeypatch=monkeypatch)
    with pytest.raises(ParametrosCotizacionError, match="no numérico"):
        cargar_parametros(2026)


def test_validar_acepta_ejercicio_correcto():
    _validar(_EJ_OK, "2026")        # no lanza


# ── Multi-ejercicio + cálculo sigue funcionando ────────────────────────────────
def test_calculo_consistente_entre_ejercicios():
    from src.rrhh.nomina_motor import NominaInput, calcular_nomina
    e = NominaInput(salario_base_mensual=2000, grupo_cotizacion="1", irpf_tipo=15)
    r25 = calcular_nomina(e, cargar_parametros(2025))
    r26 = calcular_nomina(e, cargar_parametros(2026))
    # mismas bases; difiere MEI (0.13 vs 0.15) → SS trabajador 2026 ligeramente mayor
    assert r25.bccc == r26.bccc == 2000.0
    assert r26.ss_trabajador["mei"] > r25.ss_trabajador["mei"]
