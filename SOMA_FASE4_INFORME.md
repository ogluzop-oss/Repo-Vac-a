# SOMA — COPILOTO IA · INFORME TÉCNICO FASE 4 (Inteligencia contextual y proactiva)

Objetivo: que SOMA **observe continuamente** el ERP y decida **cuándo merece la pena intervenir**,
como un responsable de operaciones. Todo **reutilizando** la infraestructura existente; sin sistemas
paralelos, sin bloquear la UI, sin ejecutar acciones automáticamente. Arquitectura F1/F2/F3 y Plan UI
Enterprise **intactos** (esta fase no modificó `main.py`: el observador arranca desde el kernel).

---

## 1. Arquitectura definitiva del SomaObserver

`src/soma/observador.py::SomaObserver` — proceso **residente dentro del SomaKernel** (`QObject`),
transparente para el usuario. Ciclo:

```
Event Bus (tiempo real) ─┐
Scheduler (periódico) ───┤→ _disparar_analisis (throttled) → hilo daemon → razonamiento.recopilar()
                         │         → _elegir (filtro) → hallazgo_listo (señal) → HILO PRINCIPAL
                         │                                         → kernel.intervenir()
```

- Análisis en **segundo plano** (hilo daemon) → no bloquea la UI ni ralentiza el ERP.
- Resultado al **hilo principal** por señal Qt (`hallazgo_listo`) → seguro para overlay/TTS.
- Nunca ejecuta acciones: solo **sugiere** (todo sigue por Workflow/Gobierno/Autonomía).

Archivos nuevos (solo `src/soma/`): `observador.py`, `razonamiento.py`, `prioridad.py`.
Extensiones del kernel: `intervenir()`, explicabilidad, arranque/parada del observador, filtro.

## 2. Integración con Event Bus

El observador se **suscribe a `*`** del Event Bus existente. Cualquier evento relevante (ventas,
kárdex, incidencias, sincronización…) dispara un análisis **throttled** (mín. 45 s entre pasadas) →
observación **continua y en tiempo real sin temporizadores propios de sondeo**.

## 3. Integración con Scheduler

Se **reutiliza el Scheduler**: el observador `registra` su función y un `registrar_job`
(`soma_observacion`, intervalo 1 h) y ejecuta el job **a través de** `scheduler.ejecutar_job(...)`
(queda en el historial del Scheduler). Un único latido (~90 s) activa ese job durante la sesión, para
que las comprobaciones periódicas se apoyen en el Scheduler existente (no en timers dispersos).

## 4. Integración con PredictionService

`razonamiento.analizar_predicciones` reutiliza `prediccion.servicio()` (`riesgos`, `stock`, …) y las
**interpreta**: no dice "stock bajo", sino *"hay N artículos en riesgo de quedarse sin stock; si el
consumo se mantiene, faltarán antes de la reposición"* + consecuencias + acción sugerida.

## 5. Integración con Gemelo Digital

`razonamiento.analizar_gemelo` usa `gemelo.servicio().estado_empresa()` (estado por dominios +
alertas + riesgo) para detectar y explicar situaciones relevantes de la operativa.

## 6. Integración con Workflow

`razonamiento.analizar_workflow` cuenta instancias `wf_instancias` en curso/pendientes y avisa de
posibles **cuellos de botella** (≥5 → MEDIA, ≥10 → ALTA) con acción sugerida (abrir la bandeja).

## 7. Integración con Auditoría

`razonamiento.analizar_auditoria` detecta **errores repetidos** (≥10 en 24 h) en `auditoria_logs` y
lo plantea como **recomendación** (nunca acusación): "quizá hay un proceso que conviene revisar".

## 8. Integración con Centro de Inteligencia (KPIs)

`razonamiento.analizar_kpis` reutiliza el cuadro de mando (`bi.dashboard.panel`) — p.ej. liquidez
estimada a 90 días negativa → ALTA. **No recalcula**: interpreta los KPIs ya calculados por BI.

## 9. Sistema de prioridades

`src/soma/prioridad.py`: `MUY_BAJA · BAJA · MEDIA · ALTA · CRITICA`. Solo **ALTA/CRÍTICA** provocan
auto-invocación (`UMBRAL_INTERVENCION`). Mapeo `riesgo→prioridad` para reutilizar los niveles de
Predicción/Gemelo.

## 10. Motor de razonamiento

`src/soma/razonamiento.py`: cada fuente produce **Hallazgos EXPLICABLES** con `titulo`, `mensaje`
(natural, no alarmista), `prioridad`, `dominio`, **`por_que` / `datos` / `consecuencias` / `accion`**.
Interpreta, no informa. Tono ayudante ("He detectado algo que creo que deberías revisar…").

## 11. Sistema de auto-invocación

`kernel.intervenir(hallazgo)` (hilo principal) reutiliza **el mismo flujo** que la invocación del
usuario: `activar(motivo="observador")` → overlay + personaje + estados + conversación + voz. **No hay
un segundo sistema visual.** El mensaje se muestra en el overlay y se dice por voz (pose Explicando
hasta terminar).

### Filtro de interrupciones (no saturar)
- Solo prioridad ≥ ALTA.
- **Cooldown** por aviso (30 min) — no repetir el mismo (memoria de observación, dedup por clave).
- **No molestar** si: SOMA ya está activo · el usuario **acaba de cerrar** SOMA (<90 s) · **límite de
  frecuencia** entre intervenciones automáticas (180 s).

### Memoria de observación (sesión)
El observador recuerda qué avisos **mostró** (y permite marcar aceptado/ignorado/resuelto), evitando
repeticiones. Se pierde al cerrar la app (sesión), como se pidió.

## 12. Gestión de explicabilidad

Tras una intervención, si el usuario pregunta *"¿por qué me dices esto? / ¿en qué datos te basas? /
¿qué consecuencias?"*, el kernel responde con el **`por_que` + `datos` + `consecuencias` + `accion`**
del último hallazgo (nunca "porque sí"). Verificado.

---

## 13. Verificaciones realizadas

| Verificación | Resultado |
|---|---|
| SomaObserver funciona continuamente | ✅ residente, Event Bus + Scheduler + latido |
| No hay procesos duplicados | ✅ reutiliza Predicción/Gemelo/Workflow/Auditoría/BI/Event Bus/Scheduler |
| Scheduler reutilizado | ✅ `registrar` + `registrar_job` + `ejecutar_job` (historial del Scheduler) |
| Event Bus alimenta al observador | ✅ suscripción `*` throttled |
| PredictionService integrado e interpretado | ✅ hallazgos razonados (rotura/sobrestock/riesgos) |
| Gemelo Digital | ✅ alertas por dominio interpretadas |
| KPIs interpretados | ✅ vía BI (liquidez 90 d, etc.) |
| Workflow monitorizado | ✅ cuellos de botella (pendientes) |
| Auditoría | ✅ errores repetidos como recomendación |
| SOMA solo interrumpe cuando merece la pena | ✅ umbral ALTA + filtro no-molestar |
| Sin avisos repetitivos innecesarios | ✅ cooldown + memoria de observación |
| Explicaciones comprensibles | ✅ por_que/datos/consecuencias |
| Rendimiento estable (no bloquea UI) | ✅ análisis en hilo daemon, throttled |
| Sin fugas de memoria | ✅ hilos efímeros; un solo latido; overlay único |
| Overlay sigue funcionando | ✅ reutilizado por la auto-invocación |
| Plan UI Enterprise intacto | ✅ `git status`: solo módulos SOMA; `main.py` sin cambios en F4 |

Verificación E2E: 9 hallazgos reales del ERP · intervención auto-invoca el overlay · segunda
intervención inmediata **ignorada** (SOMA activo) · explicabilidad responde con porqué+datos · mismo
aviso **filtrado por cooldown** · **smoke `5 passed`**.

## 14. Posibles mejoras para la Fase 5

- **Razonamiento con tendencias %**: enriquecer los mensajes con la variación exacta ("+18 %, 2 días")
  cuando `prediccion.tendencias` la aporte.
- **Diferencias realidad vs simulación** (Gemelo + Simulador) como hallazgo explicable.
- **Detección de "usuario trabajando intensamente"** más fina (ritmo de eventos) para el filtro.
- **Aprendizaje de preferencias**: si el usuario ignora repetidamente un tipo de aviso, bajar su
  prioridad (memoria de observación → ajuste adaptativo).
- **Respuestas multimodales**: mostrar la evidencia con componentes Enterprise (tabla/tarjeta) además
  del texto.
- **Persistencia** de la memoria de observación entre sesiones (opcional).

---

## Estado

**Fase 4 completada y verificada.** SOMA observa el ERP en segundo plano, razona sobre datos reales,
prioriza, decide cuándo intervenir sin saturar y explica sus recomendaciones — reutilizando toda la
inteligencia existente y sin ejecutar nada por su cuenta. No se inicia ninguna fase posterior hasta tu
revisión y aprobación.
