# Helm chart — Smart Manager AI (backend)

Chart de Helm del backend Enterprise. **Aditivo**: reutiliza la imagen del `Dockerfile` (gunicorn
`wsgi:app` en `:8000`) sin sobrescribir el comando ni cambiar `docker-compose`/`gunicorn`/CI. Parametriza
los mismos recursos que `deploy/k8s` (ConfigMap, Secret, Deployment, Service, Ingress, HPA) con probes
apuntando a los endpoints reales `/api/v1/live` y `/api/v1/ready`.

## Instalación

```bash
# Producción: usa un Secret gestionado fuera de git.
helm upgrade --install smart-manager deploy/helm/smart-manager \
  --namespace smart-manager --create-namespace \
  --set image.tag=1.0.0 \
  --set ingress.host=api.midominio.com \
  --set secrets.existingSecret=smart-manager-secrets

# Pruebas rápidas (genera el Secret desde values; NO en producción):
helm upgrade --install smart-manager deploy/helm/smart-manager \
  --namespace smart-manager --create-namespace \
  --set secrets.create=true
```

## Valores principales (`values.yaml`)

| Clave | Descripción | Defecto |
|-------|-------------|---------|
| `image.repository` / `image.tag` | Imagen del backend | `smart-manager/backend` / `latest` |
| `replicaCount` | Réplicas (si HPA off) | `2` |
| `autoscaling.enabled` | HPA CPU/memoria | `true` (2–10) |
| `service.port` | Puerto del Service | `80` → `8000` |
| `ingress.enabled` / `ingress.host` | Ingress + host | `true` / `api.smart-manager.local` |
| `probes.livenessPath` / `readinessPath` | Endpoints de probe | `/api/v1/live` / `/api/v1/ready` |
| `config.*` | Variables NO sensibles (ConfigMap) | DB_HOST, DB_NAME, ... |
| `secrets.existingSecret` | Secret gestionado (recomendado) | `""` |

## Render / validación

```bash
helm lint deploy/helm/smart-manager
helm template smart-manager deploy/helm/smart-manager
```
