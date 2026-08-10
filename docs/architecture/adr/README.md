# Architecture Decision Records (ADR)

Registro indexado de las decisiones de arquitectura del ERP Enterprise. Cada ADR documenta una decisión
**ya vigente** (arquitectura congelada), su contexto y sus consecuencias. Formato: Contexto · Decisión ·
Consecuencias · Estado. Estado por defecto: **Aceptado** (decisión en vigor).

| ADR | Título | Estado |
|-----|--------|--------|
| [0001](0001-arquitectura-api-first-por-capas.md) | Arquitectura API-First por capas | Aceptado |
| [0002](0002-motores-unicos-n7.md) | Motores únicos — prohibido motores paralelos (N7) | Aceptado |
| [0003](0003-strangler-y-migraciones-reversibles.md) | Patrón Strangler + migraciones numeradas reversibles | Aceptado |
| [0004](0004-multitenancy-estricta.md) | Multitenancy estricta (tenant desde el token) | Aceptado |
| [0005](0005-platform-capabilities-fachada-degradable.md) | `platform.capabilities` como fachada degradable | Aceptado |
| [0006](0006-event-bus-y-event-registry.md) | Event Bus + Event Registry de UI | Aceptado |
| [0007](0007-seguridad-rbac-jwt-secret-manager.md) | Seguridad: RBAC/ACL + JWT/API Keys + Secret Manager | Aceptado |
| [0008](0008-adapter-pattern-provider-agnostic.md) | Adapter Pattern provider-agnostic para canales/conectores | Aceptado |
| [0009](0009-ui-enterprise-shell.md) | UI Enterprise Shell (foundation → components → panels → windows) | Aceptado |
| [0010](0010-convencion-rest-paginacion.md) | Convención REST de paginación/orden/filtrado (E1) | Aceptado |
| [0011](0011-conectores-enterprise.md) | Conectores Enterprise oficiales (E2) | Aceptado |
| [0012](0012-sdk-oficial-desde-openapi.md) | SDK oficial distribuible desde OpenAPI (E3) | Aceptado |
| [0013](0013-despliegue-kubernetes-helm.md) | Despliegue Kubernetes/Helm reutilizando la imagen Docker (E4) | Aceptado |

## Cómo añadir un ADR

1. Copia la plantilla ([`template.md`](template.md)), numera el archivo (`NNNN-titulo-en-kebab.md`).
2. Rellena Contexto/Decisión/Consecuencias/Estado.
3. Añade la fila a esta tabla. No se reescriben ADR antiguos: si una decisión cambia, se crea un ADR
   nuevo que **supersede** al anterior (y se marca el estado del viejo como *Reemplazado por NNNN*).
