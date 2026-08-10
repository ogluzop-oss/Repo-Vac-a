# AUTOMATION_ENGINE_ENTERPRISE

## Paquete Enterprise 4 — Motor de Automatización Empresarial
### Orquestación · Decisiones · Acciones Inteligentes · Smart Manager AI

> El ERP deja de solo **detectar** y pasa a **actuar**: propone, prepara, encadena, pide
> aprobación y ejecuta (cuando está autorizado), **reutilizando** todo el ecosistema Enterprise.
> Estado: **implementado y verificado** (smoke 5/5, read-only sobre el ERP, aditivo).

---

## 1. Arquitectura
Módulo nuevo `src/services/automatizacion/` con **`AutomationService` como cerebro único**
(SUBFASE 4.1). **Nunca actúa directamente**: decide *qué / cuándo / prioridad / si requiere
aprobación / si puede ejecutarse*. **Asíncrono** (SUBFASE 4.12): se invoca desde el scheduler o
un hilo daemon, **nunca en la ruta de TPV/Facturación**.

Migración aditiva **0092** (2 tablas de estado propio, no duplican datos del ERP):
`automatizaciones_reglas` (configurables/priorizadas/activables/versionables) +
`automatizaciones_ejecuciones` (auditoría, panel y explicabilidad).

## 2. Reutilización absoluta (sin duplicar motores) — SUBFASE 4.11
| Necesidad | Se reutiliza |
|---|---|
| Aprobaciones / tareas | **Workflow/BPM** existente (`workflow_engine.iniciar_proceso`) |
| Avisos / tareas / incidencias | **notificaciones.emitir** (feeds Centro/Badges) |
| Propuestas de compra | **reabastecimiento.crear_propuesta** (propuestas, no pedidos reales) |
| Disparo por evento | **Event Bus** (Fase 1) |
| Disparo por predicción | **PredictionService** (Enterprise 3) |
| Datos | **ia.adaptadores** (read-only) |
| Programación horaria | **scheduler** existente |
| Visualización | **Centro de Actividad** (bloque IA) |
**No se crea** un segundo Workflow/BPM/motor de tareas/scheduler.

## 3. Reglas (SUBFASE 4.2)
Reglas **SI (condición) ENTONCES (acción)**, configurables, priorizadas, activables y
**versionables** (`reglas.configurar` incrementa versión). Catálogo semilla (7 reglas):
`R_STOCK_CRITICO → propuesta compra`, `R_IMPAGO_30D → tarea administración`,
`R_SIN_VENTAS_120 → proponer liquidación`, `R_CONTRATO_30D → tarea RRHH`,
`R_PRED_ROTURA → propuesta`, `R_RIESGO_IMPAGO → tarea admin`, `R_PRECIO_EVENTO → notificar`.
Condiciones reutilizan IA/Predicción (`stock_critico`, `prediccion_rotura`, `impago_30d`,
`sin_ventas_120d`, `contrato_caduca_30d`, `riesgo_impago_alto`).

## 4. Acciones inteligentes (SUBFASE 4.5)
Catálogo reutilizable y **ampliable** (`registrar_accion`): `notificar`, `crear_tarea`,
`crear_recordatorio`, `crear_incidencia`, `solicitar_aprobacion`, `crear_propuesta_compra`,
`proponer_liquidacion`, `solicitar_inventario/auditoria/revision`, `enviar_correo`. Cada acción
**delega** en un subsistema existente; ninguna hace escrituras críticas directas.

## 5. Automatizaciones (disparadores)
- **Por evento (4.3)**: `procesar_evento({tipo})` → reglas `evento` → acción → Centro/Badge. ✔ (R_PRECIO_EVENTO → INFORMADA)
- **Por predicción (4.4)**: `procesar_predicciones()` → reglas `prediccion`. ✔ (R_RIESGO_IMPAGO → PROPUESTA)
- **Programadas (4.6)**: `procesar_programadas(cuando)` vía scheduler (diario/semanal/mensual). ✔ (R_IMPAGO_30D → PROPUESTA)
- **Encadenadas (4.7)**: framework `cadenas` (pasos + pasos con aprobación que **pausan** en Workflow). ✔ (cadena `reposicion_predictiva` → PENDIENTE_APROBACION)

## 6. Niveles de automatización (SUBFASE 4.8)
`informar` / `proponer` / `aprobar` (Workflow) / `auto`. **Las acciones críticas
(`crear_pedido`, `enviar_correo`, `crear_factura`) NUNCA se ejecutan en auto sin
`set_auto_critico(True)`** — se degradan a propuesta. ✔ (R_PRECIO_EVENTO en `auto` → EJECUTADA)

## 7. Explicabilidad y auditoría (SUBFASE 4.10)
Cada ejecución registra **por qué / qué regla / qué evento o predicción / qué acción / nivel /
usuario / fecha / resultado** en `automatizaciones_ejecuciones`. **Idempotente**: una ejecución
por (regla, disparador, día) — `INSERT IGNORE` por hash. ✔ (re-ejecución mismo día no duplica)

## 8. Panel de automatizaciones (SUBFASE 4.9)
`panel.resumen` → ejecutadas/propuestas/informadas/pendientes/aprobadas/rechazadas/fallidas,
**tiempo ahorrado** (min) y última ejecución; `panel.listar` → detalle explicable. Integrado en
el **Centro de Actividad** (bloque IA muestra "⚙️ N automatizaciones (min ahorrados)"). ✔

## 9. Rendimiento (SUBFASE 4.12)
`procesar_async` ejecuta el tick en un **hilo daemon**; los disparadores se invocan desde el
scheduler/eventos, **nunca inline** en TPV/Facturación/Inventario/Sincronización. Consultas
indexadas; idempotencia evita reprocesos.

## 10. Compatibilidad (SUBFASE 4.13)
**Smoke 5/5 verde.** No se modifica Verifactu, AEAT, Facturación, hashes, snapshots,
numeraciones, motor fiscal, Workflow, Distribución, Centro de Actividad, IA ni PredictionService.
**Solo se añaden capacidades.** Multiempresa/multitienda (todo filtra `id_empresa`), idempotente,
reversible (`revertir`), retrocompatible.

## 11. Pruebas ejecutadas
Siembra de 7 reglas; disparo por programado/evento/predicción; explicabilidad registrada;
idempotencia (mismo día sin duplicar); niveles (auto → EJECUTADA, crítica degradada); cadena con
pausa de aprobación; panel (total 4, 20 min ahorrados); config on/off; Centro con panel de
automatización; smoke.

## 12. Escalabilidad y puntos preparados para futuras ampliaciones
- Reglas y acciones **enchufables** (`registrar_accion`, catálogo en BD por empresa) → miles de
  reglas sin tocar el motor.
- Condiciones nuevas se añaden al registro `CONDICIONES` sin cambiar `AutomationService`.
- Cadenas declarativas (`cadenas.definir`) → flujos arbitrarios sin código fijo.
- Listo para **auto-ejecución gobernada por RBAC/Workflow**, colas asíncronas dedicadas y
  motores de decisión ML (sobre PredictionService) sin rediseño.

---

**Motor de Automatización Empresarial implementado y verificado.** Smart Manager AI ahora
**anticipa y actúa** de forma auditable y segura, reutilizando por completo el ecosistema
Enterprise (Event Bus · Distribución · Centro de Actividad · IA · Predicción · Workflow/BPM) sin
comprometer ninguna certificación anterior.
