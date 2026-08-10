"""
Runner de PRUEBAS DE CARGA (Etapa F · Fase F7). Ejecuta el harness sobre los 8 subsistemas y escribe
`docs/PRUEBAS_CARGA_F7.md`. Uso:

    QT_QPA_PLATFORM=offscreen DB_NAME=smart_manager_test python tests/load/run_load.py [N]

NO modifica lógica: solo invoca operaciones existentes (mayormente lectura, N acotado) y las cronometra.
"""

import importlib.util
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tests.load.harness import medir, medir_throughput, tabla, tabla_throughput  # noqa: E402

EMP = os.getenv("SM_LOAD_EMP", "LOAD-F7")


def _sdk_client():
    raiz = pathlib.Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "sm_sdk_load", raiz / "sdk" / "python" / "smartmanager" / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def _t(method, url, params, cuerpo, headers):
        return (200, {"data": [], "next_cursor": None})
    return mod.Client("http://x/api/v1", token="T", transporte=_t)


def _ops():
    ops = []

    # API (superficie REST real, endpoint público)
    try:
        from src.api import crear_app
        cli = crear_app().test_client()
        ops.append(("API (/system/version)", lambda: cli.get("/api/v1/system/version")))
    except Exception as e:
        print("API no disponible:", e)

    # Marketplace
    try:
        from src.services import marketplace
        ops.append(("Marketplace (catalogo)", lambda: marketplace.catalogo(EMP)))
    except Exception as e:
        print("Marketplace:", e)

    # SDK
    try:
        c = _sdk_client()
        ops.append(("SDK (communications.list)", lambda: c.communications.list(limit=10)))
    except Exception as e:
        print("SDK:", e)

    # Scheduler
    try:
        from src.services.scheduler_enterprise import core as sch
        ops.append(("Scheduler (listar_schedules)", lambda: sch.listar_schedules(EMP)))
    except Exception as e:
        print("Scheduler:", e)

    # Event Bus (lectura de suscripciones / dispatch)
    try:
        from src.services import eventbus
        ops.append(("Event Bus (suscripciones)", lambda: eventbus.suscripciones()))
    except Exception as e:
        print("Event Bus:", e)

    # Comercio Digital
    try:
        from src.services import comercio_digital as cd
        ops.append(("Comercio Digital (descriptor)", lambda: cd.descriptor()))
    except Exception as e:
        print("Comercio Digital:", e)

    # BI
    try:
        from src.services.observabilidad import operacional
        ops.append(("BI/Observabilidad (snapshot)", lambda: operacional.snapshot(EMP)))
    except Exception as e:
        print("BI:", e)

    # IA
    try:
        from src.services.ia import recomendaciones
        ops.append(("IA (recomendaciones)", lambda: recomendaciones.generar(id_empresa=EMP)))
    except Exception as e:
        print("IA:", e)

    return ops


def main(n=300, *, segundos=2.0, concurrencia=8):
    ops = _ops()
    resultados = [medir(fn, n=n, nombre=nombre) for nombre, fn in ops]
    print(tabla(resultados))
    # THROUGHPUT sostenido (R6): tx/min por operación con `concurrencia` hilos durante `segundos`.
    thr = [medir_throughput(fn, segundos=segundos, concurrencia=concurrencia, nombre=nombre)
           for nombre, fn in ops]
    print("\n### Throughput sostenido (tx/min)\n")
    print(tabla_throughput(thr))
    doc = pathlib.Path(__file__).resolve().parents[2] / "docs" / "PRUEBAS_CARGA_F7.md"
    return {"latencia": resultados, "throughput": thr}, doc


if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    res, _ = main(N)
