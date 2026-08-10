# Informe Técnico — Módulo 1: Clientes / CRM (Enriquecimiento funcional)

**Metodología:** auditoría → informe → implementar solo lo que falta → pruebas → verificación.
**Invariantes:** sin módulos nuevos, sin reescribir, sin duplicar, todo aditivo/reversible. SOMA, Plan
UI Enterprise y navegación aprobada intactos.

## 1. Auditoría — qué existía ya (NO se ha tocado)

El CRM ya era muy completo (ramas VTA + DR/CRM). Verificado en código:

| Propuesta | Estado previo | Dónde |
|---|---|---|
| historial comercial | ✅ | `clientes_gui` (ventas/devoluciones/saldo) |
| historial de llamadas | ✅ | `crm/actividades` tipo `llamada` |
| reuniones | ✅ | `crm/actividades` tipo `reunion` (+ evento de calendario) |
| oportunidades · pipeline · embudos | ✅ | `crm/oportunidades`, `crm/pipeline` (`embudo`) |
| segmentación | ✅ | `clientes.segmento` |
| scoring | ✅ | `crm/crm_scoring`, `puntuar_lead` |
| recordatorios | ✅ | `crm/automatizacion` (recordatorio_comercial, lead_sin_respuesta) |
| presupuestos | ✅ | `db/ventas_comercial` |
| documentos · contratos · archivos | ✅ | Centro Documental / módulo Contratos |
| tareas · actividades | ✅ | `services.tareas` + `crm/actividades` (llamada/email/reunion/visita/seguimiento/demo) |
| previsión de ventas | ✅ | `crm/analitica.forecast_comercial` |
| fidelización · programas de puntos | ✅ | `db/fidelizacion`, `clientes.saldo_puntos/saldo_monedero` |
| automatizaciones | ✅ | `crm/automatizacion` + AutomationService |

## 2. Diferencias encontradas — qué faltaba (implementado ahora)

| Propuesta | Estado | Acción |
|---|---|---|
| campañas / marketing | ❌ ausente | **nuevo** `crm/campanias.py` + tablas |
| objetivos comerciales | ❌ ausente | **nuevo** `crm/objetivos.py` + tabla |
| geolocalización | ❌ ausente | **columnas** `clientes.latitud/longitud` |
| rutas comerciales | ❌ ausente | **nuevo** `crm/rutas.py` + tablas |
| pedidos vinculados | ❌ ausente | **ampliación** `crm/oportunidades.vincular_venta` (+ `id_venta`) |

## 3. Funcionalidades reutilizadas (no duplicadas)

- **Campañas** reutilizan `clientes` (segmentación de destinatarios) y el sistema de correo/comunicaciones para el envío por canal.
- **Objetivos** calculan el REAL reutilizando `ventas`, `crm_oportunidades` (ganadas) y `crm_actividades` (visitas) — sin recalcular ni duplicar métricas.
- **Rutas** reutilizan la geolocalización de `clientes` y, al marcar una visita, `crm/actividades` (que a su vez crea tarea + evento de calendario). Optimización por vecino más cercano (haversine).
- **Pedidos vinculados** reutilizan la venta existente (no la crean); solo enlazan `oportunidad ↔ venta` y marcan la oportunidad ganada.
- Integración transversal: **Auditoría** (`log_auditoria`) y **Event Bus** (`eventos.publicar`) en cada operación → visibles para SOMA/BI/Workflow/Historial. Multiempresa por `id_empresa`.

## 4. Funcionalidades nuevas (resumen técnico)

- migr **0102**: `clientes +latitud/longitud`; `crm_oportunidades +id_venta`; tablas `crm_campanias`,
  `crm_campania_destinatarios`, `crm_objetivos`, `crm_rutas`, `crm_ruta_paradas`.
- `crm/campanias.py`: crear · añadir_destinatarios_por_segmento · activar · resultados · listar.
- `crm/objetivos.py`: crear_objetivo · progreso (objetivo vs real por ventas/oportunidades/visitas).
- `crm/rutas.py`: set_geolocalizacion · crear_ruta · añadir_parada · optimizar (haversine) ·
  marcar_visitada (crea actividad) · listar_rutas · paradas.
- `crm/oportunidades.py`: +`vincular_venta` · `ventas_de_oportunidad`.
- GUI: pestañas **Campañas · Objetivos · Rutas** en `CRMDashboardWindow` (reutiliza `_tabla`).

## 5. Pruebas realizadas y superadas

- migr 0102 aplicada. Campaña creada + 22 destinatarios por segmento + activar + listar. Objetivo
  creado + progreso (real/pct calculados desde ventas). Ruta creada + geolocalización + parada +
  optimización + listado. `vincular_venta` OK. Event Bus sin errores. CRMDashboard construye con las 9
  pestañas (incl. Campañas/Objetivos/Rutas). **smoke 5 passed.** SOMA/UI Enterprise/navegación intactos.

## 6. Posibles mejoras futuras

- Envío real de campañas por canal (activar los conectores del Bloque 2 con credenciales).
- Objetivos: cuadro de mando dedicado en BI (hoy progreso calculado al vuelo).
- Rutas: mapa visual y export a navegador GPS; geocodificación automática de direcciones.
- Pedidos vinculados: generar la venta desde la oportunidad con un clic (hoy se vincula una existente).
