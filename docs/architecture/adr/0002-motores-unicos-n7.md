# ADR-0002: Motores únicos — prohibido motores paralelos (N7)

- **Estado**: Aceptado
- **Fecha**: 2026-07-18 (invariante permanente del proyecto)

## Contexto

El ERP incorpora capacidades transversales (aprobaciones, reglas, tareas programadas, eventos, IA,
observabilidad, permisos, secretos…). Reimplementarlas en cada módulo produce duplicación, comportamiento
divergente y deuda técnica.

## Decisión

**Existe un único motor por capacidad y se reutiliza siempre** (regla N7). Motores canónicos:

- Workflow (`services/workflow`) · Rules (`services/rules`) · Scheduler (`scheduler_enterprise`)
- Event Bus (`services/eventbus`) · IA (`services/ia` + `services/inteligencia`)
- Observabilidad (`services/observabilidad`) · RBAC (`services/autorizacion` + `services/seguridad`)
- Secret Manager (`seguridad.secret_manager`) · Marketplace (`services/marketplace`) · SDK (`src/sdk`)
- Conexiones/Adaptadores (`comercio_digital.conexiones` + Adapter Pattern) · BI (`bi`/`bi_corp`)

Antes de implementar cualquier capacidad nueva se **audita** si ya existe; si existe, se reutiliza. Crear
un motor paralelo está prohibido salvo justificación arquitectónica documentada en un ADR.

## Consecuencias

- (+) Comportamiento coherente y una sola fuente de verdad por capacidad.
- (+) Menor superficie de mantenimiento y pruebas.
- (−) Obliga a auditar antes de construir y a integrar (no reinventar), aunque parezca más lento.

## Alternativas consideradas

- Motores por módulo: descartado por duplicación y divergencia funcional.
