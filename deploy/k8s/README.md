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
