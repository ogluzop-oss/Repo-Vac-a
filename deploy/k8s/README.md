# Kubernetes — manifiestos del backend (Etapa E · Fase E4)

Manifiestos crudos del backend Enterprise. **Aditivos**: reutilizan la imagen del `Dockerfile`
(gunicorn `wsgi:app` en `:8000`) sin sobrescribir el comando ni cambiar el comportamiento de
`docker-compose`/`gunicorn`/CI. Materializan la estructura que antes documentaba OBS-9 ("los
manifiestos se generan en la fase de despliegue").

## Contenido

| Manifiesto | Recurso |
|------------|---------|
| `namespace.yaml` | Namespace `smart-manager` |
| `configmap.yaml` | Variables NO sensibles (DB_HOST, DB_NAME, SM_LOG_JSON, ...) |
| `secret.yaml` | **Plantilla** de secretos (placeholders; nunca secretos reales en git) |
| `deployment.yaml` | Deployment del backend + **liveness** (`/api/v1/live`) + **readiness** (`/api/v1/ready`) |
| `service.yaml` | Service ClusterIP (80 → 8000) |
| `ingress.yaml` | Ingress (host configurable, TLS) |
| `hpa.yaml` | Autoscaling horizontal (CPU/memoria, 2–10 réplicas) |
| `kustomization.yaml` | Agrupa todo para `apply -k` |

## Despliegue

```bash
# 1) Crea los secretos REALES fuera de git (no uses el secret.yaml de ejemplo en producción):
kubectl create namespace smart-manager
kubectl -n smart-manager create secret generic smart-manager-secrets \
  --from-literal=DB_PASSWORD=... \
  --from-literal=SMART_MANAGER_JWT_SECRET=... \
  --from-literal=API_MASTER_KEY=...

# 2) Aplica el resto:
kubectl apply -k deploy/k8s
```

La base de datos (MariaDB) se asume gestionada aparte (StatefulSet o BD gestionada del cloud); ajusta
`DB_HOST` en el ConfigMap. Health/readiness/liveness usan los endpoints reales del backend
(`/api/v1/live`, `/api/v1/ready`, `/api/v1/health`).

## Observabilidad (Prometheus)

Métricas Prometheus en `/api/v1/metrics`; scrape con un `ServiceMonitor` (Prometheus Operator) apuntando
al Service `smart-manager-backend` (puerto `http`).

## Secretos de aplicación

Inyecta los secretos por entorno (no en imagen ni repo). Mínimos: `DB_PASSWORD`,
`SMART_MANAGER_JWT_SECRET`; opcional `API_MASTER_KEY`. Para el envío vía **Gmail API (OAuth)** del
módulo de correo corporativo se pueden añadir `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`
(recomendado por variables de entorno). Orden de resolución del client OAuth en runtime:
env → secret manager → `GOOGLE_OAUTH_CLIENT_FILE` → `documentos/google_oauth_client.json` (fallback
heredado). Los tokens OAuth se guardan **cifrados (Fernet)** en BD; nunca en el contenedor ni en el repo.

Alternativa con **Helm**: ver [`deploy/helm/smart-manager`](../helm/smart-manager/).
