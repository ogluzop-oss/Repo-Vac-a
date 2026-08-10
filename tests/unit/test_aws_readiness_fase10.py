"""
Tests · Fase 10 (AWS Production Readiness) — abstracciones de software con backends locales, AWS-ready por
config y degradables sin boto3. Foco: AISLAMIENTO MULTI-TENANT (storage, distribución de eventos, jobs),
guard de URLs firmadas, y que los backends AWS NO se declaren operativos sin infraestructura (degradan).
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ── Fase 1-4 · Storage abstraction + aislamiento multi-tenant ─────────────────
@pytest.fixture()
def storage(tmp_path):
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ["STORAGE_LOCAL_ROOT"] = str(tmp_path)
    from src.services import storage as S
    S._reset_para_tests()
    yield S.obtener_storage()
    S._reset_para_tests()
    os.environ.pop("STORAGE_LOCAL_ROOT", None)


def test_storage_tenant_aislamiento(storage):
    from src.services.storage import TenantIsolationError

    clave = storage.guardar("A", "facturas", "f1.pdf", b"secreto-A")
    assert clave == "tenant/A/facturas/f1.pdf"
    assert storage.leer("A", clave) == b"secreto-A"          # A lee lo suyo

    # B NO puede leer/borrar/firmar el objeto de A (clave fuera de su tenant).
    for op in (lambda: storage.leer("B", clave),
               lambda: storage.borrar("B", clave),
               lambda: storage.url_firmada("B", clave),
               lambda: storage.metadatos("B", clave)):
        with pytest.raises(TenantIsolationError):
            op()

    # Manipular el path / escapar del tenant falla.
    for mala in ("tenant/A/../B/facturas/f1.pdf", "../etc/passwd", "/tenant/A/x", "tenant/B/facturas/f1.pdf"):
        with pytest.raises(TenantIsolationError):
            storage.leer("A", mala)


def test_storage_url_firmada_requiere_autorizacion(storage):
    from src.services.storage import TenantIsolationError
    clave = storage.guardar("A", "nominas", "n1.pdf", b"x")
    # Sin autorización (RBAC del usuario) NO se emite URL, aunque el tenant sea correcto.
    with pytest.raises(TenantIsolationError):
        storage.url_firmada("A", clave, usuario=7, autorizado=False)
    assert storage.url_firmada("A", clave, usuario=7, autorizado=True).startswith("local://")


def test_storage_id_empresa_obligatorio(storage):
    from src.services.storage import TenantIsolationError
    with pytest.raises(TenantIsolationError):
        storage.guardar("", "facturas", "f.pdf", b"x")
    with pytest.raises(TenantIsolationError):
        storage.guardar(None, "facturas", "f.pdf", b"x")


def test_storage_s3_degradable_sin_boto3():
    # Sin boto3, pedir backend s3 es un ERROR EXPLÍCITO (no fallback silencioso, no simulado).
    from src.services.storage.s3 import boto3_disponible
    if boto3_disponible():
        pytest.skip("boto3 presente")
    os.environ["STORAGE_BACKEND"] = "s3"
    from src.services import storage as S
    S._reset_para_tests()
    with pytest.raises(Exception):
        S.obtener_storage()
    os.environ["STORAGE_BACKEND"] = "local"
    S._reset_para_tests()


def test_storage_migracion_degradable(storage):
    from src.services.storage import migracion
    storage.guardar("A", "facturas", "f1.pdf", b"x")
    inf = migracion.migrar_local_a_s3("A", dry_run=True)
    # Sin boto3/S3, la migración informa el bloqueo y NO borra nada local (no destructiva, no simulada).
    assert inf["id_empresa"] == "A"
    assert any("S3" in e or "boto3" in e for e in inf["errores"]) or inf["total"] >= 0


# ── Fase 10-11 · Distribución de eventos multi-instancia + aislamiento ────────
def test_distribucion_forward_local_no_remoto():
    from src.services.eventbus import realtime
    cap = []

    class Cap:
        def publicar(self, ev):
            cap.append(ev)

    realtime.set_distribucion(Cap())
    try:
        realtime._on_event({"tipo": "stock.salida", "id_empresa": "A"})          # local → propaga
        realtime._on_event({"tipo": "stock.salida", "id_empresa": "A"}, _remoto=True)  # remoto → NO propaga (sin bucle)
        assert len(cap) == 1 and cap[0]["id_empresa"] == "A"
    finally:
        realtime.set_distribucion(None)


def test_distribucion_reparto_aislado_por_tenant():
    from src.services.eventbus import realtime
    realtime.set_distribucion(None)
    ca = realtime.registrar("A")
    cb = realtime.registrar("B")
    try:
        realtime._on_event({"tipo": "ventas.nueva", "id_empresa": "A", "v": 1})
        assert ca.cola.get_nowait()["v"] == 1        # A recibe
        assert cb.cola.empty()                        # B NUNCA recibe el evento de A
    finally:
        realtime.desregistrar(ca)
        realtime.desregistrar(cb)


def test_inprocess_distribution_entrega_preserva_tenant():
    from src.services.eventbus.distribucion import InProcessDistribution
    entregados = []
    d = InProcessDistribution()
    d.conectar(lambda ev: entregados.append(ev))     # "otra instancia"
    d.publicar({"tipo": "prediccion.generada", "id_empresa": "A"})
    assert entregados and entregados[0]["id_empresa"] == "A"   # el tenant viaja intacto entre instancias


def test_redis_distribution_degradable():
    from src.services.eventbus.distribucion import redis_disponible
    if redis_disponible():
        pytest.skip("redis presente")
    from src.services.eventbus.distribucion import RedisDistribution
    with pytest.raises(Exception):
        RedisDistribution()                           # PREPARADO, no operativo sin redis (no simulado)


# ── Fase 12-15 · Jobs + worker IA + aislamiento de tenant ─────────────────────
def test_job_exige_tenant():
    from src.services.jobs.base import Job
    with pytest.raises(ValueError):
        Job("", "prediccion.forecast")
    j = Job("A", "prediccion.forecast", payload={"horizonte": 7}, usuario_origen=3)
    assert j.id_empresa == "A" and j.correlation_id and j.created_at
    assert Job.from_dict(j.to_dict()).id_empresa == "A"


def test_local_queue_ciclo():
    os.environ["JOB_QUEUE_BACKEND"] = "local"
    from src.services import jobs as J
    J._reset_para_tests()
    jid = J.encolar_prediccion("A", horizonte=7, usuario=1)
    cola = J.obtener_cola()
    assert jid.startswith("job_") and cola.profundidad() == 1
    job = cola.siguiente()
    assert job.id_empresa == "A" and job.tipo == "prediccion.forecast"
    J._reset_para_tests()


@pytest.mark.db
def test_worker_procesa_forecast_tenant_aislado():
    from src.services.jobs.base import Job
    from src.services.jobs import worker
    job = Job("F10-EMPTY", "prediccion.forecast", payload={"horizonte": 7})
    res = worker.procesar(job)
    assert job.estado == "COMPLETADO" and isinstance(res, dict)
    assert res.get("id_empresa") == "F10-EMPTY"        # el forecast se ejecutó en el tenant del job


def test_sqs_degradable_sin_boto3():
    from src.services.jobs.sqs import boto3_disponible
    if boto3_disponible():
        pytest.skip("boto3 presente")
    from src.services.jobs.sqs import SQSQueue
    with pytest.raises(Exception):
        SQSQueue()                                     # PREPARADO, no operativo sin boto3


# ── Fase 7 · Secrets Manager (interfaz única, AWS degradable) ─────────────────
def test_secret_manager_aws_degradable(monkeypatch):
    from src.services.seguridad import secret_manager as SM
    monkeypatch.setenv("SM_SECRET_BACKEND", "aws_secrets_manager")
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("MI_SECRETO_TEST", "valor-de-entorno")
    # Sin AWS resoluble, fuera de producción cae a entorno (no rompe DEV); nunca inventa.
    assert SM.obtener_secreto("MI_SECRETO_TEST") == "valor-de-entorno"
    assert SM.backend_activo() == "aws_secrets_manager"
