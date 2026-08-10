# ADR-0009: UI Enterprise Shell (foundation → components → panels → windows)

- **Estado**: Aceptado
- **Fecha**: 2026-07-18

## Contexto

La UI de escritorio crecía con tablas/tarjetas/buscadores/toolbars duplicados y lógica de negocio
mezclada, dificultando la coherencia visual y el mantenimiento.

## Decisión

La UI Enterprise se organiza en capas con dependencia estricta
`foundation → components → panels → windows` (foundation **nunca** depende de components):

- `gui/foundation/`: primitivas (`tokens`, `icons`, `permissions`, `export`, `events`, `shell`).
- `gui/components/`: librería visual única (`EnterpriseTable/Card/Toolbar/Search/Filter/DashboardGrid/
  Timeline/StatusBadge/RiskIndicator`).
- Reglas: toda pantalla nueva usa `QtEnterpriseWindow`/`QtEnterprisePanel` y la librería; **sin lógica de
  negocio en la GUI**; pestañas con lazy loading; deprecación por ciclos (Strangler).

## Consecuencias

- (+) Coherencia visual y reutilización; separación UI/negocio.
- (+) Framework-agnostic en `foundation` (shell desacoplado de Qt).
- (−) Prohíbe crear widgets fuera de la librería salvo justificación documentada.
