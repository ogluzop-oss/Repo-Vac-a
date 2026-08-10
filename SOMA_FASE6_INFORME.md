# SOMA — COPILOTO IA · INFORME TÉCNICO FASE 6 (Mission Engine · Orquestación de Especialistas IA)

Objetivo: SOMA deja de ser conversacional y actúa como **Director de Orquesta** — recibe OBJETIVOS,
los convierte en MISIONES, las descompone, coordina a los Especialistas IA (en paralelo), consolida
una única respuesta y solicita aprobaciones para lo crítico. **El usuario habla solo con SOMA.** Todo
reutilizando la arquitectura F1–F5 (congelada) y la infraestructura Enterprise; async, sin bloquear la
UI. Plan UI Enterprise **intacto** (F6 no tocó `main.py`).

---

## 1. Arquitectura completa del Mission Engine

`src/soma/mission/` (paquete nuevo; el resto se reutiliza):

```
Objetivo (usuario → SOMA)
   → MissionEngine.crear()  → plantillas.detectar/construir → Misión (tareas + dependencias)
   → MissionEngine.iniciar() → orquestación en HILO DE FONDO:
        while pendientes:
            listas = tareas con dependencias satisfechas  → SUBMIT al ThreadPool (PARALELO)
            al completar cada una → estado + mensaje natural + workspace + persistencia
   → _consolidar() → UNA respuesta coherente (dedup + fuentes + tabla)
   → señales Qt (actualizada/mensaje/terminada) → HILO PRINCIPAL → overlay/voz
```

- `modelo.py`: `Mision` + `Tarea` (estados, dependencias, progreso, prioridad).
- `plantillas.py`: descomposición por plantilla (abrir_tienda / mejorar_ventas / reducir_costes).
- `motor.py`: `MissionEngine` (QObject singleton `engine()`): crear/iniciar/pausar/reanudar/cancelar,
  ejecución paralela (ThreadPool), consolidación, prioridad+cola, historial, explicabilidad.

## 2. Auditoría de reutilización

| Reutiliza | Uso |
|---|---|
| **AgentManager** (Especialistas IA) | Cada tarea de dominio se delega al especialista (`manager().delegar`) |
| **Simulador** | Tarea "simulación" (impacto what-if VIRTUAL) |
| **PredictionService** | Tarea "predicción" (riesgos/demanda) |
| **Gemelo Digital** | Tarea "gemelo" / estado + síntesis |
| **Autonomía + Workflow + Gobierno** | Tarea "aprobación": crea plan gobernado, **espera aprobación** |
| **Scheduler / Event Bus** | Ya usados por el observador (F4); base de disparo/monitorización |
| **SomaKernel** (memoria/contexto/personalidad/overlay) | Presentación, voz, memoria de trabajo |
| **Componentes Enterprise** | Workspace y respuestas visuales (tabla/KPIs) |
| **BD** | Historial de misiones (`soma_misiones`, `soma_mision_tareas`, migr 0098) |

**Sin duplicidades**: no hay segundo orquestador, razonador, memoria ni contexto.

## 3. Componentes nuevos creados

`src/soma/mission/{__init__,modelo,plantillas,motor}.py`, `src/gui/soma/workspace.py`
(MissionWorkspace), migración `0098_soma_misiones`. Extensiones del panel de conversación
(`mostrar_workspace`) y del contrato del espacio (`mostrar_workspace`). Extensiones del kernel
(routing de misión, control, explicabilidad, handlers de señales).

## 4. Integración con SomaKernel

`kernel.procesar` enruta: explicabilidad (misión/hallazgo) → colaboración → **control de misión**
("¿cómo va?"/pausa/continúa/cancela) → continuidad → fast-path → **creación de misión** (objetivo
complejo) → planificación/tareas → cerebro. Señales del motor conectadas a: `_on_mision_actualizada`
(workspace), `_on_mision_mensaje` (SOMA narra el progreso + aparece si hace falta), `_on_mision_terminada`
(respuesta consolidada). El kernel sigue siendo el **único interlocutor**.

## 5. Integración con AgentManager

Cada tarea con dominio de especialista se resuelve con `AgentManager.delegar(dominio, objetivo, ctx)`.
Los especialistas **nunca hablan con el usuario**: SOMA recoge sus resultados y los consolida. Los
dominios especiales (simulación/predicción/gemelo/aprobación) usan su servicio concreto.

## 6. Sistema de planificación

`plantillas.py` descompone el objetivo en tareas con **dependencias** (DAG), especialista asignado,
paralelización y ETA. Ejemplo "abrir tienda" → financiero · predicción · stock · rrhh (en paralelo) →
simulación (depende de financiero+predicción) → workflow/aprobación (depende del resto). Verificado:
6 tareas con dependencias correctas.

## 7. Sistema de coordinación

El motor recorre el DAG: lanza en paralelo las tareas cuyas dependencias están satisfechas, espera,
desbloquea dependientes y repite. Cada transición emite estado + mensaje natural + actualización del
workspace + persistencia. Verificado: fin/pred/stock/rrhh → HECHA; sim tras ellas; wf al final.

## 8. Sistema de ejecución paralela

`ThreadPoolExecutor` (4 hilos): las tareas independientes se ejecutan **simultáneamente** (RRHH mientras
Tesorería mientras Predicción mientras Compras). El orquestador vive en un hilo de fondo; **no bloquea
la UI**; los resultados vuelven por señales Qt. Verificado.

## 9. Workspace de Misión

`MissionWorkspace` (dentro del overlay, sin ventanas nuevas): objetivo + lista de tareas con
**estado (✓/⟳/⏳/✗/•), especialista y progreso**, actualizado en vivo por `actualizada`. Verificado:
27 actualizaciones durante una misión.

## 10. Gestión de prioridades

Misiones con prioridad `CRITICA/ALTA/NORMAL/BAJA`. Si hay una en curso, las nuevas se **encolan** y se
lanzan por prioridad al terminar la actual (`_siguiente_en_cola`). El usuario recibe aviso de encolado.

## 11. Gestión del historial

Persistencia en `soma_misiones` (objetivo, plantilla, prioridad, estado, especialistas, resultado,
aprobaciones, errores, duración, fechas) y `soma_mision_tareas` (por tarea). **Misiones, no
conversaciones.** Verificado: misión persistida con estado `ESPERANDO_APROBACION` y `aprobaciones=1`.

## 12. Gestión de explicabilidad

"¿Por qué has decidido esto?" → `engine.explicar`: qué **especialistas** consultó, cómo **descompuso**
el objetivo, que ejecutó en paralelo lo independiente y **consolidó**, y que lo crítico quedó a la
espera de aprobación. Nunca "porque sí". Verificado.

## 13. Verificaciones realizadas

| Verificación | Resultado |
|---|---|
| No hay duplicidades | ✅ reutiliza AgentManager/Simulador/Predicción/Gemelo/Autonomía/Workflow/BD |
| Reutiliza AgentManager | ✅ `delegar` por dominio |
| Reutiliza Scheduler | ✅ (observador F4) + base de disparo |
| Reutiliza Workflow/Gobierno | ✅ la tarea crítica pasa por Autonomía→Workflow→Gobierno |
| Reutiliza CopilotService | ✅ vía kernel para consultas no-misión |
| SOMA único interlocutor | ✅ los especialistas no hablan con el usuario |
| Workspace desde cualquier módulo | ✅ overlay top-level (F2) |
| Sin fugas de memoria | ✅ hilos daemon/pool; señales; motor/overlay únicos |
| Misiones pausables | ✅ `pausar` (flag respetado por el bucle) |
| Misiones cancelables | ✅ `cancelar` (no ejecuta nada crítico) |
| Misiones reanudables | ✅ `reanudar` |
| Tareas paralelas | ✅ ThreadPool; independientes a la vez |
| Sin regresiones F1–F5 | ✅ **smoke `5 passed`** |
| Plan UI Enterprise intacto | ✅ `git status`: solo SOMA + migración; F6 sin cambios en `main.py` |
| Seguridad (crítica → aprobación) | ✅ tarea `aprobacion` → `ESPERANDO_APROBACION`, nunca ejecuta |
| Consolidación (una respuesta) | ✅ dedup + fuentes + tabla; no respuestas por especialista |

## 14. Posibles mejoras para la siguiente fase

- **Reanudación tras reinicio**: retomar misiones `ESPERANDO_APROBACION` desde el historial al arrancar.
- **Ejecución de lo aprobado**: cuando Workflow/Gobierno aprueben, continuar la misión automáticamente
  (siempre gobernado por Autonomía Supervisada).
- **Más plantillas** de misión y **descomposición asistida por CopilotService** para objetivos libres.
- **Conflictos entre especialistas**: reglas de resolución más ricas en el consolidador.
- **Workspace interactivo**: pulsar una tarea para ver su detalle/fuentes.
- **Prioridad dinámica** y estimación de tiempos más precisa.

---

## Estado

**Fase 6 completada y verificada.** SOMA convierte objetivos en misiones, descompone, coordina a los
Especialistas IA en paralelo, consolida una única respuesta, muestra el Workspace en el overlay,
gestiona prioridad/cola/historial, es pausable/reanudable/cancelable y deja lo crítico a la espera de
aprobación — reutilizando toda la arquitectura, sin bloquear la UI y sin ejecutar nada crítico por su
cuenta. No se inicia ninguna fase posterior hasta tu revisión y aprobación.
