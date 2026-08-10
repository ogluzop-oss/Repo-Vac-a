# SOMA — COPILOTO IA · INFORME TÉCNICO FASE 3 (Cerebro conversacional e integración funcional)

Objetivo: **conectar** todo lo ya existente para que SOMA mantenga conversaciones reales y ejecute
acciones, reutilizando íntegramente el SomaKernel (F1), el Overlay/Character Pack (F2) y la
infraestructura Enterprise. **Sin** pantallas nuevas. Plan UI Enterprise y arquitectura F1/F2
**intactos** (solo cambios aditivos en `main.py` y extensiones de los módulos SOMA).

---

## 1. Integración definitiva con CopilotService

- El kernel expone `procesar(texto, origen)` como **punto de entrada único** (voz y texto). Para todo
  lo que no sea navegación simple, **delega en `CopilotService.preguntar`** (cerebro real). Se eliminó
  la conversación simulada del overlay (el stub "estoy en construcción" ya no existe).
- La llamada al cerebro es **asíncrona** (hilo daemon) y su resultado vuelve al **hilo principal** por
  un **puente Qt** (`_PuenteRespuesta`, `pyqtSignal`) → seguro para UI/TTS.
- La respuesta se **muestra en el overlay** (`espacio.mostrar_respuesta`) y se **dice por voz**.

## 2. Integración con AgentManager (Especialistas IA)

- No se crea ningún sistema paralelo: `CopilotService` **ya delega por dominio en el `AgentManager`**
  (11 especialistas: ventas/crm, compras, stock, tesorería/financiero, rrhh, fiscal, logística, tpv,
  auditoría) y **coordina varios** cuando la consulta lo requiere ("¿qué debería hacer hoy?"). SOMA
  aprovecha ese enrutado tal cual.

## 3. Funcionamiento del sistema conversacional

Flujo: entrada (voz/texto) → `kernel.procesar` → (fast-path navegación | `CopilotService`) →
`PENSANDO` → respuesta → `HABLANDO`/`CONFIRMACION` + voz → `ESPERANDO` (feliz). Verificado end-to-end:
consulta *"¿qué ha pasado hoy?"* → respuesta REAL del cerebro *"Hoy: sin actividad relevante."*
mostrada y hablada.

## 4. Gestión del contexto

- `ScreenContext` (F1) aporta en vivo **usuario, empresa, tienda, almacén, módulo activo, pantalla
  activa, permisos, idioma**; el kernel resuelve usuario/empresa y los pasa a `CopilotService`
  (`preguntar(texto, usuario, id_empresa)`), que a su vez resuelve su propio contexto. El módulo/
  pantalla se actualizan por lectura viva y por el Event Registry (`UI_PANEL_*`).

## 5. Gestión de la memoria

- Memoria de **sesión** reutilizando `copilot.memoria` (que `CopilotService` ya usa) + registro en
  `SomaKernel.memoria` de cada consulta/respuesta. No persistente (se pierde al cerrar), como se pidió.

## 6. Sistema de acciones

- **Navegación / acciones simples** (abrir, cerrar, volver al menú): **fast-path** de baja latencia
  vía `_SomaNavegador` (adaptador que **reutiliza** `menu_principal.abrir_ventana_por_id` /
  `setCurrentWidget` / cierre existentes; sin duplicar navegación). Tras ejecutar, SOMA **se aparta**
  (repliega a reposo).
- **Acciones críticas**: nunca se ejecutan directas. Se canalizan por `copilot.acciones`, que ya
  delega en **Workflow + Gobierno + Autonomía Supervisada** respetando permisos (filosofía Enterprise
  intacta). SOMA **propone**; la organización decide.

## 7. Gestión de voz

- **Conectada de extremo a extremo**: `SomaWorker` (wake word + STT) → `kernel` → `CopilotService` →
  `SomaTTS` → Overlay.
  - Wake word (`_soma_on_activado`) → `kernel.activar()` → aparece + **ESCUCHANDO** (con margen para
    dictar, ~6 s antes de asentar en feliz).
  - Comando de voz no reconocido por el fast-parser → `kernel.procesar` → **CopilotService** (antes
    decía "no te he entendido"; ahora responde de verdad).
  - Comandos de navegación/consulta reconocidos → fast-path existente (baja latencia).
  - **Pose HABLANDO/EXPLICANDO** se mantiene **hasta que la voz termina de verdad** (`voz.hablar`
    sondea `SomaTTS.hablando`), y vuelve a **feliz**.

## 8. Interrupción

- `kernel.procesar` **interrumpe** cualquier discurso en curso al recibir una nueva entrada
  (`voz.interrumpir()` → `SomaTTS.detener`), y `kernel.interrumpir()` corta y deja a SOMA a la
  escucha. El usuario nunca queda bloqueado.

## 9. Personalidad y expresiones

- Se implementa `src/soma/personality` (los contratos de F1): `Personalidad.modular()` da un tono
  **profesional y cercano** (sutil, no chatbot) y elige la **expresión** del personaje según el tipo
  (respuesta → HABLANDO, confirmación → CONFIRMACION, error → ERROR). Las expresiones se **sincronizan
  automáticamente** con la conversación (el kernel fija el estado; el personaje lo representa).

## 10. Gestión de errores y logging

- **Errores**: si el cerebro/especialista falla, SOMA muestra la pose **ERROR**, da un mensaje
  **empático** ("…puedo intentarlo de otra manera") y **sigue** la conversación (nunca rompe el flujo).
- **Logging** (sistema existente): se registran consulta, `intent`, **especialista/fuentes**, **tiempo
  de respuesta (ms)**, acciones ejecutadas y errores.

---

## Optimización / duplicidades (§15)

- La inteligencia conversacional pasa **exclusivamente** por `CopilotService` (overlay de texto +
  voz no reconocida). No hay segundo cerebro para esa vía.
- El fast-path de navegación **reutiliza** `soma_engine.parsear_comando` (parser ligero) + la
  navegación existente del ERP → sin duplicar. `soma_engine`/`soma_queries` quedan como camino rápido
  para comandos/consultas reconocidos por voz (baja latencia).

---

## Verificaciones realizadas

| Verificación | Resultado |
|---|---|
| SOMA mantiene conversaciones reales | ✅ texto → CopilotService → respuesta real mostrada y hablada |
| Memoria durante toda la sesión | ✅ `copilot.memoria` + `SomaKernel.memoria` |
| Contexto se actualiza al cambiar de módulo | ✅ ScreenContext + Event Registry (`UI_PANEL_*`) |
| Especialistas IA responden | ✅ vía AgentManager (delegación/coordinación automática) |
| Navegación funciona | ✅ fast-path `_SomaNavegador` (reutiliza navegación existente) |
| Voz funciona (inicio/escucha/proceso/respuesta/cancelación/interrupción) | ✅ worker↔kernel↔copilot↔TTS↔overlay |
| Interrupción de respuestas | ✅ `voz.interrumpir()` al recibir nueva entrada |
| Acciones críticas respetan Workflow/Gobierno | ✅ vía `copilot.acciones` (sin canal paralelo) |
| Overlay sigue funcionando | ✅ reposo/activo, atenuación, captador de clics, poses |
| Sin fugas de memoria | ✅ hilos daemon efímeros; timers con tope; overlay único |
| Sin regresiones | ✅ **smoke `5 passed`** |
| Plan UI Enterprise intacto | ✅ `git status`: solo `main.py` aditivo + módulos SOMA |

---

## Posibles mejoras para la siguiente fase

- **Contexto de módulo en el prompt**: pasar explícitamente módulo/pantalla activos al `CopilotService`
  para respuestas aún más "en contexto" ("¿esto qué es?").
- **Respuestas multimodales enriquecidas**: mostrar en el overlay tablas/tarjetas (componentes
  Enterprise) cuando la respuesta traiga `datos`, no solo texto.
- **Barge-in por voz real**: detectar voz del usuario mientras SOMA habla para interrumpir sin esperar
  al fin del STT.
- **Personalidad avanzada**: poblar `tone/expressions/emotions` con más matices y sincronía gestual.
- **Memoria persistente** (opcional) entre sesiones.
- **Proactividad** (modo observador): auto-invocación ante eventos críticos (Event Bus + Predicción +
  Scheduler).

---

## Estado

**Fase 3 completada y verificada.** SOMA mantiene conversaciones reales (voz y texto) a través de
CopilotService + Especialistas IA, con contexto, memoria de sesión, acciones gobernadas, voz completa,
interrupción, personalidad, manejo de errores y logging — reutilizando toda la arquitectura existente.
No se inicia ninguna fase posterior hasta tu revisión y aprobación.
