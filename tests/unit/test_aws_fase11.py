"""
Tests · Fase 11 — correcciones AWS: H1 integración StorageProvider (persistencia documental), H2 Redis
sin self-echo, H3 idempotencia/retries de jobs, H4 IaC HCL válido. Backends locales/deterministas; sin AWS,
sin mocks presentados como infraestructura real.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ── H1 · Persistencia documental por StorageProvider ──────────────────────────
@pytest.fixture()
def storage_local(tmp_path):
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ["STORAGE_LOCAL_ROOT"] = str(tmp_path)
    from src.services import storage as S
    S._reset_para_tests()
    yield S.obtener_storage()
    S._reset_para_tests()
    os.environ.pop("STORAGE_LOCAL_ROOT", None)


def test_h1_persistir_fichero_tenant_aware(storage_local, tmp_path):
    from src.services.storage.documentos import persistir_fichero
    origen = tmp_path / "NOMINA X 2026.pdf"
    origen.write_bytes(b"contenido-nomina")

    r = persistir_fichero("A", "nominas", str(origen), nombre="NOMINA X 2026.pdf")
    assert r["ok"] and r["clave"].startswith("tenant/A/nominas/")
    # El nombre se sanea (sin espacios) y el binario es recuperable por el MISMO tenant.
    assert storage_local.leer("A", r["clave"]) == b"contenido-nomina"
    # Aislamiento: otro tenant NO puede leer esa clave.
    from src.services.storage import TenantIsolationError
    with pytest.raises(TenantIsolationError):
        storage_local.leer("B", r["clave"])


def test_h1_persistir_bulletproof_sin_fichero(storage_local):
    from src.services.storage.documentos import persistir_fichero
    # Nunca lanza aunque no exista el fichero o falte el tenant (no debe romper el registro).
    assert persistir_fichero("A", "facturas", "/no/existe.pdf")["ok"] is False
    assert persistir_fichero(None, "facturas", "/no/existe.pdf")["ok"] is False


# ── H2 · Redis sin self-echo (multi-instancia determinista) ───────────────────
def test_h2_sello_y_eco():
    from src.services.eventbus import distribucion as D
    ev = {"tipo": "stock.x", "id_empresa": "A"}
    env = D.sellar(ev, "inst-1")
    assert env["_source_instance_id"] == "inst-1" and "_source_instance_id" not in ev  # no muta el original
    assert D.es_eco(env, "inst-1") is True
    assert D.es_eco(env, "inst-2") is False


def test_h2_broker_exactamente_una_entrega_sin_self_echo():
    from src.services.eventbus.distribucion import InProcessBroker
    recibidos = {"A": [], "B": [], "C": []}
    broker = InProcessBroker()
    broker.conectar("A", lambda ev: recibidos["A"].append(ev))
    broker.conectar("B", lambda ev: recibidos["B"].append(ev))
    broker.conectar("C", lambda ev: recibidos["C"].append(ev))

    entregas = broker.publicar({"tipo": "ventas.nueva", "id_empresa": "T1"}, origen="A")
    assert entregas == 2                       # B y C (NO A: self-echo descartado)
    assert len(recibidos["A"]) == 0            # la instancia origen NO recibe su propio eco
    assert len(recibidos["B"]) == 1 and len(recibidos["C"]) == 1   # exactamente una vez cada una
    assert recibidos["B"][0]["id_empresa"] == "T1"                 # tenant intacto
    assert "_source_instance_id" not in recibidos["B"][0]          # sello de transporte limpiado


# ── H3 · Idempotencia y retries de jobs ───────────────────────────────────────
@pytest.fixture()
def jobs_reset():
    from src.services import jobs as J
    J._reset_para_tests()
    yield
    J._reset_para_tests()


def test_h3_idempotencia_no_reejecuta(jobs_reset, monkeypatch):
    from src.services.jobs import worker
    from src.services.jobs.base import Job
    llamadas = {"n": 0}
    monkeypatch.setattr(worker, "_despachar", lambda job: llamadas.__setitem__("n", llamadas["n"] + 1) or {"ok": True})

    job = Job("A", "prediccion.forecast")
    assert worker.procesar(job).get("ok") and job.estado == "COMPLETADO"
    assert llamadas["n"] == 1
    # Reentrega del MISMO job_id (SQS at-least-once) → NO se re-ejecuta.
    r2 = worker.procesar(job)
    assert r2.get("duplicado") is True and llamadas["n"] == 1


def test_h3_error_permanente_no_reintenta(jobs_reset, monkeypatch):
    from src.services.jobs import worker
    from src.services.jobs.base import Job, JobErrorPermanente

    def _boom(job):
        raise JobErrorPermanente("payload inválido")
    monkeypatch.setattr(worker, "_despachar", _boom)
    r = worker.procesar(Job("A", "prediccion.forecast"))
    assert r["ok"] is False and r.get("permanente") is True


def test_h3_error_temporal_agota_a_dlq(jobs_reset, monkeypatch):
    from src.services.jobs import worker
    from src.services.jobs.base import Job, JobErrorTemporal
    monkeypatch.setenv("JOB_MAX_ATTEMPTS", "1")

    def _temp(job):
        raise JobErrorTemporal("recurso momentáneo")
    monkeypatch.setattr(worker, "_despachar", _temp)
    # Con 1 intento máximo, el temporal se agota → DLQ (no reintento infinito).
    r = worker.procesar(Job("A", "prediccion.forecast"))
    assert r["ok"] is False and r.get("dlq") is True


def test_h3_tipo_no_soportado_es_permanente(jobs_reset):
    from src.services.jobs import worker
    from src.services.jobs.base import Job
    r = worker.procesar(Job("A", "tipo.inexistente"))
    assert r["ok"] is False and r.get("permanente") is True


# ── Fase 15 · AWS_ENABLED master flag por defecto OFF (app en modo local) ─────
def test_aws_enabled_default_false(monkeypatch):
    from src.utils.aws_flags import aws_enabled
    monkeypatch.delenv("AWS_ENABLED", raising=False)
    assert aws_enabled() is False                     # por defecto la app NO usa AWS
    monkeypatch.setenv("AWS_ENABLED", "true")
    assert aws_enabled() is True
    monkeypatch.setenv("AWS_ENABLED", "false")
    assert aws_enabled() is False


# ── H4 · IaC HCL válido (sin args separados por coma) — estructura modular ────
def test_h4_hcl_sin_comas_invalidas():
    import glob
    import re
    # La IaC es modular: escanea TODOS los .tf (raíz + módulos). HCL no admite `arg = x, arg2 = y`.
    ficheros = glob.glob("infra/aws/**/*.tf", recursive=True)
    assert ficheros, "no se encontraron ficheros .tf en infra/aws"
    # Bug H4 = argumentos de BLOQUE separados por coma (p. ej. `{ type = string, default = x }`). Los literales
    # de objeto (`{ type = "text", x = 0 }`), for-expressions (`for k, v`) y strings SÍ admiten comas en HCL,
    # por lo que el patrón se restringe a tipo TF barepalabra seguido de coma + otro argumento de bloque.
    for ruta in ficheros:
        with open(ruta, encoding="utf-8") as f:
            tf = f.read()
        mal = re.search(r"=\s*(string|bool|number|list|map|any)\s*,\s*(type|default|description)\s*=", tf)
        assert not mal, f"HCL con argumentos de bloque separados por coma en {ruta}"
    # Bloques clave presentes en sus ficheros correctos tras la modularización.
    with open("infra/aws/versions.tf", encoding="utf-8") as f:
        assert "terraform {" in f.read()
    with open("infra/aws/variables.tf", encoding="utf-8") as f:
        assert 'variable "aws_region"' in f.read()
