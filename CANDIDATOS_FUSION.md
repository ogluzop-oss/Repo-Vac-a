# CANDIDATOS_FUSION.md — Módulos candidatos a fusión (NO aplicar)

Fecha 2026-07-30. Lista priorizada de posibles fusiones/consolidaciones. **NO se fusiona nada** en esta fase.
Cada entrada: motivo · riesgo · dependencias · esfuerzo · beneficio. Toda fusión futura debe conservar
contratos públicos (Strangler + alias de compatibilidad).

## Candidatos a fusión / consolidación

### C1 · `services.portal` → `portal_web`
- **Motivo**: `services.portal` (infra Fase V: tipos/scopes) **no tiene frontend ni router**; `portal_web` ya
  es el Back Office. Responsabilidad huérfana solapada por nombre.
- **Riesgo**: BAJO (poco fan-in; `services.portal` casi sin consumidores). **Dependencias**: RBAC/auditoría.
- **Esfuerzo**: BAJO. **Beneficio**: ALTO (elimina un "portal" de los 5, reduce confusión).

### C2 · `services.scheduler` + `scheduler_enterprise` + `scheduler_registry` → paquete `scheduler/`
- **Motivo**: tres módulos hermanos (motor + schedules + catálogo) para un mismo concepto.
- **Riesgo**: MEDIO (muchos jobs registrados; fachadas públicas usadas). **Dependencias**: jobs de varios
  dominios, RBAC, `db`. **Esfuerzo**: MEDIO. **Beneficio**: MEDIO-ALTO (un solo "scheduler" con submódulos).

### C3 · `services.ia` + `services.prediccion` + `services.inteligencia` → paraguas `ia/{analisis,prediccion,decisiones}`
- **Motivo**: 3 capas IA con nombres poco distinguibles (documentadas como no-paralelas).
- **Riesgo**: MEDIO (fan-in alto en `prediccion`=47, `ia`=29). **Dependencias**: BI, gemelo, Event Bus.
- **Esfuerzo**: MEDIO-ALTO. **Beneficio**: MEDIO (claridad del namespace; sin cambio funcional).

### C4 · `services.stock` (IOC) + `services.inventario`
- **Motivo**: dos "enriquecimientos" de inventario; posible solape de fronteras.
- **Riesgo**: BAJO-MEDIO. **Dependencias**: `articulos`(fuente única), kárdex. **Esfuerzo**: BAJO.
  **Beneficio**: MEDIO (menos ambigüedad stock/inventario).

### C5 · `services.produccion` + `services.mrp` → `fabricacion/`
- **Motivo**: fabricación repartida (ejecución OF vs planificación/BOM).
- **Riesgo**: MEDIO (integración con kárdex oficial). **Dependencias**: kárdex/lotes. **Esfuerzo**: MEDIO.
  **Beneficio**: MEDIO.

### C6 · Consolidar "cloud": `platform.cloud` + `cloud_manager` + `observabilidad.cloud` + `saas_global`
- **Motivo**: concepto "cloud" disperso en 4 sitios. **Riesgo**: BAJO (mayormente prep/latente).
- **Dependencias**: SaaS, observabilidad. **Esfuerzo**: MEDIO. **Beneficio**: MEDIO (superficie más clara).

### C7 · `services.eventos` + `services.eventbus` (unificar nomenclatura, no el código)
- **Motivo**: 2 "buses" por nombre (bus interno + fachada Corporate + realtime). **Riesgo**: ALTO (fan-in
  enorme; el bus es núcleo). **Dependencias**: casi todo. **Esfuerzo**: ALTO (o solo renombrar/alias).
  **Beneficio**: MEDIO. **Recomendación**: NO fusionar; **clarificar con glosario/ADR** (menor riesgo).

## Resumen de priorización

| ID | Fusión | Riesgo | Esfuerzo | Beneficio | Recomendación |
|---|---|---|---|---|---|
| C1 | services.portal → portal_web | Bajo | Bajo | Alto | **Primero** |
| C4 | stock + inventario | Bajo-Medio | Bajo | Medio | Pronto |
| C6 | consolidar cloud | Bajo | Medio | Medio | Cuando se aborde cloud |
| C2 | scheduler ×3 | Medio | Medio | Medio-Alto | Con alias |
| C5 | produccion + mrp | Medio | Medio | Medio | Evaluar |
| C3 | ia/prediccion/inteligencia | Medio | Medio-Alto | Medio | Namespacing, no fusión dura |
| C7 | eventos + eventbus | Alto | Alto | Medio | **Solo glosario/ADR** |

**Nota**: ninguno es urgente; el mayor ROI/menor riesgo es **C1**. El resto, por Strangler y con la suite verde.
