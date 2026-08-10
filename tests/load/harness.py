"""
Harness de PRUEBAS DE CARGA in-process (Etapa F · Fase F7).

Sin infraestructura externa: ejercita los subsistemas reales en proceso y mide latencia (p50/p95/p99)
y throughput (ops/s). NO modifica lógica: solo invoca operaciones existentes (mayormente de lectura,
con N acotado) y cronometra. Degradable: los errores por llamada se cuentan, no rompen la medición.
"""

from __future__ import annotations

import threading
import time


def medir(fn, n: int = 500, *, warmup: int = 10, nombre: str = "") -> dict:
    """Ejecuta `fn` `n` veces midiendo la latencia de cada llamada. Devuelve estadísticas."""
    for _ in range(max(0, warmup)):
        try:
            fn()
        except Exception:
            pass
    tiempos = []
    errores = 0
    t0 = time.perf_counter()
    for _ in range(n):
        t = time.perf_counter()
        try:
            fn()
        except Exception:
            errores += 1
        tiempos.append(time.perf_counter() - t)
    total = time.perf_counter() - t0
    tiempos.sort()

    def _pct(p):
        if not tiempos:
            return 0.0
        idx = min(len(tiempos) - 1, int(round((p / 100) * (len(tiempos) - 1))))
        return tiempos[idx] * 1000  # ms

    return {"nombre": nombre, "n": n, "errores": errores,
            "ops_por_s": round(n / total, 1) if total > 0 else 0.0,
            "p50_ms": round(_pct(50), 3), "p95_ms": round(_pct(95), 3),
            "p99_ms": round(_pct(99), 3),
            "min_ms": round((tiempos[0] * 1000) if tiempos else 0.0, 3),
            "max_ms": round((tiempos[-1] * 1000) if tiempos else 0.0, 3),
            "total_s": round(total, 3)}


def medir_throughput(fn, *, segundos: float = 2.0, concurrencia: int = 8, nombre: str = "") -> dict:
    """Mide THROUGHPUT SOSTENIDO: `concurrencia` hilos ejercitan `fn` en bucle durante `segundos` y se
    cuentan las operaciones COMPLETADAS → tx/min (y ops/s). Sirve para demostrar capacidad de volumen
    (R6) en local, sin desplegar en cloud. Degradable: los errores por llamada se cuentan, no rompen la
    medición. Honestidad: es una medida IN-PROCESS contra una única BD local — no equivale a una prueba
    de escala en cloud; da una cota inferior reproducible del rendimiento del stack de servicios."""
    concurrencia = max(1, int(concurrencia))
    fin = time.perf_counter() + max(0.1, float(segundos))
    contadores = [0] * concurrencia
    errores = [0] * concurrencia
    barrera = threading.Barrier(concurrencia + 1)

    def _worker(i):
        barrera.wait()
        ok, err = 0, 0
        while time.perf_counter() < fin:
            try:
                fn()
                ok += 1
            except Exception:
                err += 1
        contadores[i], errores[i] = ok, err

    hilos = [threading.Thread(target=_worker, args=(i,), daemon=True) for i in range(concurrencia)]
    for h in hilos:
        h.start()
    barrera.wait()
    t0 = time.perf_counter()
    for h in hilos:
        h.join()
    total_s = time.perf_counter() - t0
    ops = sum(contadores)
    errs = sum(errores)
    ops_s = round(ops / total_s, 1) if total_s > 0 else 0.0
    return {"nombre": nombre, "concurrencia": concurrencia, "segundos": round(total_s, 3),
            "ops": ops, "errores": errs, "ops_por_s": ops_s, "tx_min": int(round(ops_s * 60))}


def tabla(resultados: list) -> str:
    """Formatea los resultados como tabla Markdown."""
    cab = ("| Subsistema | N | ops/s | p50 (ms) | p95 (ms) | p99 (ms) | errores |\n"
           "|------------|---|-------|----------|----------|----------|---------|\n")
    filas = "".join(
        f"| {r['nombre']} | {r['n']} | {r['ops_por_s']} | {r['p50_ms']} | {r['p95_ms']} | "
        f"{r['p99_ms']} | {r['errores']} |\n" for r in resultados)
    return cab + filas


def tabla_throughput(resultados: list) -> str:
    """Formatea resultados de throughput (tx/min) como tabla Markdown."""
    cab = ("| Operación | Concurrencia | Duración (s) | ops | ops/s | tx/min | errores |\n"
           "|-----------|--------------|--------------|-----|-------|--------|---------|\n")
    filas = "".join(
        f"| {r['nombre']} | {r['concurrencia']} | {r['segundos']} | {r['ops']} | {r['ops_por_s']} | "
        f"{r['tx_min']} | {r['errores']} |\n" for r in resultados)
    return cab + filas


__all__ = ["medir", "medir_throughput", "tabla", "tabla_throughput"]
