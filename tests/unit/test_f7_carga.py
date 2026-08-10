"""
Tests Etapa F · Fase F7: harness de pruebas de carga (smoke).

Verifica el harness de medición (estadísticas + conteo de errores) y una medición real ligera sobre un
subsistema, SIN ejecutar la carga completa (esa va por `tests/load/run_load.py`, fuera de la suite).
No modifica lógica.
"""

import importlib.util
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[2]


def _harness():
    spec = importlib.util.spec_from_file_location("f7_harness", RAIZ / "tests" / "load" / "harness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_harness_mide_estadisticas():
    h = _harness()
    r = h.medir(lambda: sum(range(100)), n=30, warmup=2, nombre="cpu")
    assert r["n"] == 30 and r["errores"] == 0
    assert r["ops_por_s"] > 0
    for k in ("p50_ms", "p95_ms", "p99_ms", "min_ms", "max_ms"):
        assert k in r and r[k] >= 0
    assert r["p95_ms"] >= r["p50_ms"] >= 0             # percentiles ordenados


def test_harness_cuenta_errores():
    h = _harness()
    estado = {"i": 0}

    def _fn():
        estado["i"] += 1
        if estado["i"] % 2 == 0:
            raise ValueError("boom")

    r = h.medir(_fn, n=10, warmup=0, nombre="err")
    assert r["errores"] == 5                            # la mitad fallan; no rompe la medición


def test_harness_tabla_markdown():
    h = _harness()
    r = h.medir(lambda: None, n=5, warmup=0, nombre="noop")
    md = h.tabla([r])
    assert "| Subsistema |" in md and "noop" in md


def test_medicion_real_subsistema_ligero():
    # Medición real sobre un subsistema barato (descriptor de Comercio Digital), N pequeño.
    h = _harness()
    from src.services import comercio_digital as cd
    r = h.medir(lambda: cd.descriptor(), n=20, warmup=2, nombre="cd")
    assert r["n"] == 20 and r["errores"] == 0 and r["ops_por_s"] > 0


def test_throughput_concurrente_tx_min():
    # R6: throughput sostenido con varios hilos durante una ventana corta → tx/min > 0.
    h = _harness()
    r = h.medir_throughput(lambda: sum(range(50)), segundos=0.3, concurrencia=4, nombre="cpu")
    assert r["concurrencia"] == 4 and r["errores"] == 0
    assert r["ops"] > 0 and r["ops_por_s"] > 0 and r["tx_min"] == int(round(r["ops_por_s"] * 60))
    md = h.tabla_throughput([r])
    assert "| Operación |" in md and "tx/min" in md and "cpu" in md


def test_throughput_cuenta_errores_sin_romper():
    h = _harness()

    def _fn():
        raise ValueError("boom")

    r = h.medir_throughput(_fn, segundos=0.2, concurrencia=2, nombre="err")
    assert r["ops"] == 0 and r["errores"] > 0           # todo falla, pero mide sin romper
