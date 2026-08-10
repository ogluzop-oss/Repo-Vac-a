# ADR-0005: `platform.capabilities` como fachada degradable

- **Estado**: Aceptado
- **Fecha**: 2026-07-18

## Contexto

Los servicios necesitan acceder a capacidades transversales (Event Bus, Workflow, Rules, Scheduler, IA,
Observabilidad, RBAC, Marketplace, Secret Manager, Storage, Documental, Pagos, Divisas, Fiscalidad…) sin
acoplarse a su implementación concreta ni romperse si una capacidad no está disponible.

## Decisión

Toda dependencia transversal se resuelve a través de **`src/platform/capabilities`**, una **fachada
única** que devuelve la capacidad o `None` (degradable). Los servicios comprueban disponibilidad y
degradan limpiamente; nunca importan la implementación concreta de otra capa transversal directamente
cuando existe la capacidad.

## Consecuencias

- (+) Desacoplamiento y degradación elegante (la ausencia de una capacidad no rompe el flujo).
- (+) Sustituir la implementación de una capacidad no afecta a sus consumidores.
- (−) Hay que tratar el caso `None` en cada uso.

## Alternativas consideradas

- Imports directos entre servicios: descartado por acoplamiento y fallos duros.
