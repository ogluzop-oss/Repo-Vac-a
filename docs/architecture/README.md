# Arquitectura — Smart Manager AI

Documentación de arquitectura del ERP Enterprise. **Formaliza** la arquitectura ya existente (congelada);
no introduce cambios de código. Se compone de:

- **[ADR](adr/)** — Architecture Decision Records indexados: las decisiones estructurales, su contexto y
  sus consecuencias.
- **[Diagramas](diagrams.md)** — vistas C4 (contexto/contenedores/componentes), dependencias, flujos,
  integraciones, eventos, Marketplace, SDK y API (Mermaid, se renderizan en GitHub).

## Mapa rápido

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| UI (escritorio) | `src/gui/` (`foundation → components → panels → windows`) | Presentación PyQt6; sin lógica de negocio |
| API REST/GraphQL | `src/api/` (`/api/v1`) | Superficie HTTP; consume servicios, nunca BD directa |
| Backend/WSGI | `src/backend/`, `wsgi.py` | App Flask (gunicorn) para la API/servicios |
| Servicios | `src/services/` | Lógica de negocio por dominio |
| Plataforma | `src/platform/` (`capabilities`, `registry`, `discovery`, `gateway`, `cloud`) | Fachada de capacidades + preparación microservicios |
| Datos | `src/db/`, `src/database/migraciones/` | Acceso a datos (pymysql) + migraciones numeradas |

## Invariantes (resumen)

1. **API-First**: REST/GraphQL → servicios → dominio → BD. La UI y la API solo orquestan.
2. **N7 — motores únicos**: Workflow, Rules, Scheduler, Event Bus, IA, Observabilidad, RBAC, Secret
   Manager, Marketplace, SDK, Conexiones… se **reutilizan**; prohibido crear motores paralelos.
3. **Strangler + migraciones reversibles**: sustitución incremental; nunca reescrituras completas.
4. **Multitenancy estricta**: `id_empresa` sale SIEMPRE del token/clave; aislamiento por tenant.
5. **Provider-agnostic + degradable**: adaptadores/capacidades; sin dependencia dura de proveedores.
6. **Secretos nunca en código**: cifrados con el Secret Manager Enterprise.

Ver el detalle y el porqué de cada invariante en los [ADR](adr/).
