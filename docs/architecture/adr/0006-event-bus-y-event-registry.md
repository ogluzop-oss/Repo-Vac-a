# ADR-0006: Event Bus + Event Registry de UI

- **Estado**: Aceptado
- **Fecha**: 2026-07-18

## Contexto

Los módulos deben comunicarse de forma desacoplada y auditable (integraciones, sincronización, auditoría,
automatización). Además, la UI Enterprise necesita su propio bus de eventos de presentación.

## Decisión

- **Event Bus de dominio** (`src/services/eventbus`): `publish`/`subscribe`/`replay` con `event_store`
  (persistencia + reconstrucción) y `event_registry` (catálogo de eventos estándar). Es el único bus de
  eventos de negocio (N7).
- **Event Registry de UI** (`gui/foundation/events`): publica **exclusivamente eventos de UI**
  (`PanelOpened/Closed/DataLoaded/ActionExecuted/RefreshRequested/PermissionChanged`), **nunca** eventos
  de dominio.

Los webhooks salientes firman con HMAC-SHA256 y reutilizan este bus; el Audit Replay reconstruye desde el
`event_store`.

## Consecuencias

- (+) Desacoplamiento, trazabilidad (replay) y auditoría unificada.
- (+) Separación limpia entre eventos de negocio y de presentación.
- (−) Requiere disciplina para no publicar eventos de dominio desde la UI.
