# SOMA — COPILOTO IA · INFORME TÉCNICO FASE 1 (Núcleo arquitectónico)

Fase centrada **exclusivamente en infraestructura**: un único cerebro residente. Sin overlay,
personaje, animaciones, conversación, voz interactiva, texto ni proactividad (fases posteriores).
Proyecto independiente; el plan UI Enterprise queda **intacto**.

---

## 1. Componentes creados

`src/soma/` (cerebro/servicio, sin Qt de presentación):

| Archivo | Responsabilidad |
|---|---|
| `__init__.py` | `kernel()` — accesor **singleton** del `SomaKernel` |
| `kernel.py` | **SomaKernel**: ciclo de vida, estado, contexto, memoria, coordinación, activación, comunicación |
| `estado.py` | **Máquina de estados** (9 estados) + transiciones válidas + observadores (lógica pura) |
| `contexto.py` | **ScreenContext**: usuario/empresa/tienda/almacén/módulo/pantalla/permisos/idioma (en vivo) |
| `memoria.py` | Memoria conversacional de sesión (envoltorio sobre `copilot.memoria`) |
| `voz.py` | Adaptador que envuelve `SomaWorker`/`SomaTTS` existentes (getters vivos; sin duplicar) |
| `especialistas.py` | Accesor al sistema oficial de **Especialistas IA** (= `AgentManager`) |
| `espacio.py` | Contrato del **Espacio Conversacional** + `EspacioNulo` (no-op; UI en fases posteriores) |
| `personality/` | Arquitectura de personalidad (contratos, **sin implementar**): `personality/tone/expressions/gestures/emotions` |

Enganches **aditivos** (2 líneas efectivas) en `src/main.py`:
- Al final de `_iniciar_soma()` (tras login): `soma.kernel().iniciar(self)`.
- En `closeEvent()`: `soma.kernel().shutdown()`.

---

## 2. Componentes reutilizados (sin duplicar)

| Sistema existente | Uso en SOMA |
|---|---|
| `SomaWorker` (`src/utils/soma_worker.py`) | Escucha/wake-word (referenciado por `voz.py`, no recreado) |
| `SomaTTS` (`src/utils/soma_tts.py`) | Voz (referenciado por `voz.py`) |
| `CopilotService` (`src/services/copilot`) | Cerebro conversacional (`kernel.cerebro()`) |
| `AgentManager` + especialistas (`src/services/agentes`) | **Especialistas IA** oficiales (`kernel.especialistas()`) |
| Event Bus (`src/services/eventos`) | Observación de contexto (suscripción aditiva a `*`) |
| Event Registry (`src/gui/foundation/events.py`) | Pantalla activa (`UI_PANEL_*`) |
| Scheduler (`src/services/scheduler.py`) | Base de proactividad futura (`kernel.scheduler()`) |
| `copilot.contexto` / `copilot.memoria` | Resolución de contexto y memoria |
| Ciclo de vida SOMA de `SmartManagerApp` | Punto de arranque/parada del kernel |

**Especialistas IA detectados y disponibles (11 dominios):** auditoria, compras, crm, financiero,
fiscal, logistica, rrhh, stock, tesoreria, tpv, ventas.

---

## 3. Arquitectura definitiva implementada

```
SmartManagerApp (QStackedWidget, raíz de la sesión)
   │  (login → _iniciar_soma)         (cierre → closeEvent)
   ▼                                        ▼
  soma.kernel().iniciar(self)          soma.kernel().shutdown()
   │
   ▼
SomaKernel  (SINGLETON, residente toda la sesión)
   ├─ MaquinaEstados      → 9 estados (lógica; animaciones en fase futura)
   ├─ ScreenContext       → contexto en vivo (usuario/empresa/tienda/almacén/módulo/pantalla/permisos/idioma)
   ├─ MemoriaConversacional → copilot.memoria (sesión)
   ├─ AdaptadorVoz        → SomaWorker + SomaTTS (referencia viva)
   ├─ cerebro()           → CopilotService
   ├─ especialistas()     → AgentManager (Especialistas IA)
   ├─ scheduler()         → Scheduler (proactividad futura)
   ├─ Event Bus (suscrito)→ actualiza pantalla activa
   └─ espacio             → EspacioNulo (overlay/personaje se conectan en fases posteriores)
```

**Separación estricta lógica/GUI:** `src/soma/` no importa Qt de presentación; la UI vivirá en
`src/gui/soma/` (fases posteriores) y se conectará por el contrato `EspacioConversacional` sin tocar
el núcleo.

---

## 4. Flujo completo del Kernel

1. **Login** → `SmartManagerApp._iniciar_soma()` llama `kernel().iniciar(self)` (a prueba de fallos).
2. **iniciar()** (idempotente): enlaza la app, toma referencias vivas a worker/tts, suscribe el Event
   Bus (contexto), y fija estado `DORMIDO`. El kernel queda **residente**.
3. **Residencia**: durante toda la sesión mantiene estado + contexto + memoria. (En Fase 1 no hay
   invocación real por voz/UI; la infraestructura está lista.)
4. **activar(motivo)** (infraestructura): `DORMIDO → APARECIENDO → ESCUCHANDO` y avisa al espacio
   (`EspacioNulo` = no-op). Punto de entrada único para wake word / clic / observador (fases futuras).
5. **ocultar()**: `DESAPARECIENDO → DORMIDO`; el cerebro (memoria/contexto) permanece vivo.
6. **Cierre de la app** → `closeEvent()` llama `kernel().shutdown()`: suelta la suscripción del bus,
   vuelve a `DORMIDO` y marca el kernel como no vivo. No detiene worker/tts (los gestiona la app).

---

## 5. Verificaciones realizadas

| Verificación exigida | Resultado |
|---|---|
| El kernel existe **una sola vez** (singleton) | ✅ `kernel() is kernel()` → True |
| Permanece vivo durante la sesión | ✅ `iniciar()`→`esta_vivo()`=True; idempotente |
| Reutiliza correctamente los componentes existentes | ✅ CopilotService, AgentManager (11 dominios), Scheduler, worker/tts, Event Bus |
| No hay duplicidades | ✅ Especialistas IA = AgentManager (sin registro paralelo); voz referenciada, no recreada |
| Sin regresión sobre el ERP | ✅ **smoke `5 passed`** |
| Plan UI Enterprise sin modificar | ✅ `git status`: solo `src/main.py` (aditivo) + `src/soma/` nuevo; foundation/components/paneles intactos |
| Máquina de estados (9) + transiciones | ✅ 9 estados; inválidas rechazadas; `activar/ocultar` correctos |
| Contexto completo | ✅ snapshot con los 9 campos exigidos |

Nota de entorno: la ejecución headless (offscreen, consola cp1252) no afecta al kernel; los avisos de
tablas/fuentes son del entorno de test, no del código.

---

## 6. Posibles mejoras detectadas para la Fase 2

- **Contexto por navegación**: hoy la pantalla activa se lee en vivo y por `UI_PANEL_*`. En Fase 2, al
  construir el overlay, conviene que los hosts publiquen `PanelOpened` de forma consistente para un
  contexto aún más preciso (ya soportado por el Event Registry).
- **Cerebro híbrido**: decidir el enrutado v2 (fast-path de navegación local vs. CopilotService) para
  minimizar latencia en respuestas frecuentes.
- **AdaptadorVoz**: en Fase 2/voz, mover (opcionalmente) la titularidad del worker/tts al kernel para
  centralizar el ciclo de vida, manteniendo compatibilidad con el arranque actual de `SmartManagerApp`.
- **Personalidad**: comenzar a poblar `personality/` (tono/expresiones) junto con la conversación.
- **Observador/proactividad**: registrar el primer job de `Scheduler` + suscripción filtrada del Event
  Bus (umbral ALTA/CRÍTICA) cuando se aborde la fase proactiva.
- **Espacio Conversacional**: implementar `src/gui/soma/` (overlay atenuante + captador de clics +
  personaje + animaciones) conectándolo por `kernel.set_espacio(...)`.

---

## Estado

**Fase 1 completada y verificada.** No se inicia ninguna fase posterior hasta tu revisión y
aprobación. El kernel reside, reutiliza toda la infraestructura y no ha introducido regresiones ni
tocado el plan Enterprise.
