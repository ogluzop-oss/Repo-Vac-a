"""
Tests Etapa E · Fase E4: DevOps Enterprise (Kubernetes + Helm).

Valida que los manifiestos K8s y el chart de Helm son coherentes con el backend REAL: puerto 8000,
probes hacia endpoints que EXISTEN en la app (`/api/v1/live`, `/api/v1/ready`), Service/Ingress/HPA
consistentes, Secret sin secretos reales (placeholders) y versión del chart alineada. Aditivo: no toca
Docker/compose/gunicorn/CI (se comprueba que el Dockerfile sigue usando gunicorn).
"""

import pathlib

import pytest

yaml = pytest.importorskip("yaml")

RAIZ = pathlib.Path(__file__).resolve().parents[2]
K8S = RAIZ / "deploy" / "k8s"
HELM = RAIZ / "deploy" / "helm" / "smart-manager"


def _docs(ruta):
    return [d for d in yaml.safe_load_all((ruta).read_text(encoding="utf-8")) if d]


def _uno(ruta):
    return _docs(ruta)[0]


# ── Rutas reales del backend (fuente de verdad para las probes) ────────────────
@pytest.fixture(scope="module")
def rutas_backend():
    from src.backend.app import crear_app
    app = crear_app()
    return {str(r) for r in app.url_map.iter_rules()}


def test_probes_apuntan_a_rutas_reales(rutas_backend):
    dep = _uno(K8S / "deployment.yaml")
    cont = dep["spec"]["template"]["spec"]["containers"][0]
    live = cont["livenessProbe"]["httpGet"]["path"]
    ready = cont["readinessProbe"]["httpGet"]["path"]
    assert live == "/api/v1/live" and ready == "/api/v1/ready"
    # Las rutas EXISTEN en la app Flask real (no son inventadas).
    assert live in rutas_backend and ready in rutas_backend


def test_deployment_puerto_y_envfrom():
    cont = _uno(K8S / "deployment.yaml")["spec"]["template"]["spec"]["containers"][0]
    assert cont["ports"][0]["containerPort"] == 8000
    fuentes = cont["envFrom"]
    refs = {list(f.keys())[0] for f in fuentes}
    assert refs == {"configMapRef", "secretRef"}
    # No sobrescribe el comando de la imagen (reutiliza el CMD gunicorn del Dockerfile).
    assert "command" not in cont and "args" not in cont


def test_service_targetport_http():
    svc = _uno(K8S / "service.yaml")
    p = svc["spec"]["ports"][0]
    assert p["port"] == 80 and p["targetPort"] == "http"


def test_hpa_referencia_deployment():
    hpa = _uno(K8S / "hpa.yaml")
    assert hpa["spec"]["scaleTargetRef"]["name"] == "smart-manager-backend"
    assert hpa["spec"]["minReplicas"] >= 1 and hpa["spec"]["maxReplicas"] >= hpa["spec"]["minReplicas"]
    tipos = {m["resource"]["name"] for m in hpa["spec"]["metrics"]}
    assert "cpu" in tipos


def test_ingress_enruta_al_service():
    ing = _uno(K8S / "ingress.yaml")
    backend = ing["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]
    assert backend["name"] == "smart-manager-backend"


def test_configmap_variables_clave():
    cm = _uno(K8S / "configmap.yaml")["data"]
    assert {"DB_HOST", "DB_PORT", "DB_NAME"} <= set(cm)


def test_secret_sin_secretos_reales():
    sec = _uno(K8S / "secret.yaml")
    # Plantilla: solo placeholders, nunca un secreto real versionado.
    for v in sec["stringData"].values():
        assert v == "CHANGEME"
    assert {"DB_PASSWORD", "SMART_MANAGER_JWT_SECRET"} <= set(sec["stringData"])


def test_todos_los_manifiestos_k8s_parsean():
    for f in K8S.glob("*.yaml"):
        assert _docs(f), f"manifiesto vacío/ilegible: {f}"


# ── Helm ──────────────────────────────────────────────────────────────────────
def test_helm_chart_y_values():
    chart = _uno(HELM / "Chart.yaml")
    values = _uno(HELM / "values.yaml")
    assert chart["name"] == "smart-manager" and chart["version"] == "1.0.0"
    assert values["containerPort"] == 8000
    assert values["probes"]["livenessPath"] == "/api/v1/live"
    assert values["probes"]["readinessPath"] == "/api/v1/ready"
    assert values["autoscaling"]["enabled"] is True


def test_helm_values_probes_son_rutas_reales(rutas_backend):
    values = _uno(HELM / "values.yaml")
    assert values["probes"]["livenessPath"] in rutas_backend
    assert values["probes"]["readinessPath"] in rutas_backend


def test_helm_templates_presentes():
    esperados = {"deployment.yaml", "service.yaml", "configmap.yaml", "secret.yaml", "ingress.yaml",
                 "hpa.yaml", "_helpers.tpl", "NOTES.txt"}
    presentes = {f.name for f in (HELM / "templates").glob("*")}
    assert esperados <= presentes


def test_helm_render_si_disponible(rutas_backend):
    import shutil
    import subprocess
    helm = shutil.which("helm")
    if not helm:
        pytest.skip("helm no instalado")
    out = subprocess.run([helm, "template", "smart-manager", str(HELM)],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    docs = [d for d in yaml.safe_load_all(out.stdout) if d]
    kinds = {d.get("kind") for d in docs}
    assert {"Deployment", "Service", "ConfigMap", "HorizontalPodAutoscaler"} <= kinds


# ── Aditividad: Docker/gunicorn intactos ──────────────────────────────────────
def test_dockerfile_sigue_usando_gunicorn():
    df = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    assert "gunicorn" in df and "wsgi:app" in df
