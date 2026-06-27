# Despliegue Kubernetes/Helm (OBS-9 — estructura preparada, NO desplegada)

Estructura objetivo para llevar el backend a K8s:

- `deployment.yaml`  → Deployment del backend (imagen `smart-manager-backend`), réplicas,
  `readinessProbe: /api/v1/ready`, `livenessProbe: /api/v1/live`.
- `service.yaml`     → Service ClusterIP + Ingress (TLS).
- `secret.yaml`      → DB_PASSWORD / SMART_MANAGER_JWT_SECRET (desde un gestor de secretos).
- `hpa.yaml`         → HorizontalPodAutoscaler por CPU/latencia (métricas en /api/v1/metrics).
- `mariadb`          → StatefulSet o BD gestionada externa.

Métricas Prometheus expuestas en `/api/v1/metrics`; scrape con un `ServiceMonitor`.
Esta carpeta documenta la arquitectura; los manifiestos se generan en la fase de despliegue.

## Secretos de aplicación (Secret/ConfigMap)

Inyecta los secretos por entorno (no en imagen ni repo). Mínimos: `DB_PASSWORD`,
`SMART_MANAGER_JWT_SECRET`. Opcional, para envío vía **Gmail API (OAuth)** del módulo de
correo corporativo (recomendado por variables de entorno, sin JSON en disco):

```yaml
# secret.yaml (extracto)
GOOGLE_OAUTH_CLIENT_ID: "<client-id>"
GOOGLE_OAUTH_CLIENT_SECRET: "<client-secret>"
# SM_SECRET_BACKEND: "vault"   # opcional: backend Vault/KMS (futuro)
```

Orden de resolución del client OAuth en runtime: env → secret manager → `GOOGLE_OAUTH_CLIENT_FILE`
→ `documentos/google_oauth_client.json` (fallback heredado). Los tokens OAuth se guardan
**cifrados (Fernet)** en BD; nunca en el contenedor ni en el repo.
