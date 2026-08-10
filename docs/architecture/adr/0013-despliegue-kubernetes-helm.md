# ADR-0013: Despliegue Kubernetes/Helm reutilizando la imagen Docker (E4)

- **Estado**: Aceptado
- **Fecha**: 2026-07-18 (Etapa E · Fase E4)

## Contexto

Existían `Dockerfile`, `docker-compose` y `gunicorn`, pero no manifiestos de orquestación para clúster.

## Decisión

Se añaden artefactos de despliegue en `deploy/` **sin modificar** Docker/compose/gunicorn/CI:

- **Kubernetes crudo** (`deploy/k8s`): Namespace, ConfigMap, Secret (plantilla), Deployment, Service,
  Ingress, HPA, `kustomization`.
- **Helm chart** (`deploy/helm/smart-manager`): mismos recursos parametrizados.

Ambos **reutilizan la imagen del `Dockerfile`** (gunicorn `wsgi:app` en `:8000`) sin sobrescribir el
comando; las probes usan los endpoints **reales** `/api/v1/live` (liveness) y `/api/v1/ready`
(readiness); métricas Prometheus en `/api/v1/metrics`. Los secretos se gestionan fuera de git
(`existingSecret`/gestor externo). Autoescalado por CPU/memoria.

## Consecuencias

- (+) Despliegue en clúster con dos vías equivalentes (kubectl/Helm); sin cambios de comportamiento.
- (−) La BD (MariaDB) se gestiona aparte (StatefulSet o servicio gestionado).
