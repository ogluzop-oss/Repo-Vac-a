# Deploy — Smart Manager AI (backend)

Artefactos de despliegue del backend Enterprise (API REST/servicios). Todo es **aditivo** y reutiliza
la imagen del `Dockerfile` de la raíz (gunicorn `wsgi:app` en `:8000`); no modifica
`Dockerfile`/`docker-compose`/`gunicorn`/CI ni el comportamiento del backend.

| Ruta | Qué es | Cuándo usarlo |
|------|--------|---------------|
| `../Dockerfile`, `../docker-compose.yml`, `../docker-compose.prod.yml` | Imagen + Compose (existentes) | Desarrollo / despliegue simple |
| [`k8s/`](k8s/) | Manifiestos Kubernetes crudos (`kubectl apply -k`) | Clúster sin Helm |
| [`helm/smart-manager/`](helm/smart-manager/) | Helm chart parametrizable | Clúster con Helm |

Ambas variantes despliegan el **mismo** backend con: ConfigMap (config no sensible), Secret (gestionado
fuera de git), Deployment con **liveness** (`/api/v1/live`) y **readiness** (`/api/v1/ready`), Service,
Ingress (TLS) y **HorizontalPodAutoscaler** (CPU/memoria). Métricas Prometheus en `/api/v1/metrics`.

La base de datos (MariaDB) se gestiona aparte (StatefulSet o BD gestionada del cloud); ajusta `DB_HOST`.
