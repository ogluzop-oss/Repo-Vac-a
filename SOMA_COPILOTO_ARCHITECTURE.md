# SOMA — COPILOTO IA DE SMART MANAGER AI

## Especificación maestra de arquitectura (para revisión y aprobación)

> Proyecto **independiente** del plan UI Enterprise (aprobado, cerrado e **intacto**: SOMA no lo
> modifica). **No es implementación**: requiere tu revisión y aprobación antes de escribir código.
>
> **SOMA no es un chatbot.** Es un **compañero de trabajo inteligente** que acompaña al usuario toda
> la sesión: comprende contexto/módulo/empresa/tienda/usuario/permisos/actividad, responde, ayuda,
> explica, recuerda, propone, advierte y **anticipa** problemas — reutilizando toda la arquitectura
> existente de Smart Manager AI.

---

## 0. Principio rector — dos mundos independientes

**EL CEREBRO** (proceso residente, siempre vivo, nunca desaparece): memoria · contexto · escucha ·
estado · comunicación · eventos.
**LA INTERFAZ** (el personaje): solo aparece al invocar; **nunca** contiene lógica de negocio; solo
representa visualmente el estado del asistente.

```
        SESIÓN DEL ERP (SmartManagerApp)
        ┌──────────────────────────────────────────────────────────┐
        │  SomaKernel  (RESIDENTE — nace tras login, muere al salir) │
        │   ├─ escucha (wake word)     ← SomaWorker  (reutilizado)   │
        │   ├─ voz (TTS)               ← SomaTTS     (reutilizado)   │
        │   ├─ cerebro                 ← CopilotService (reutilizado)│
        │   ├─ skills (orquestador)    ← AgentManager  (reutilizado) │
        │   ├─ observador (proactivo)  ← Event Bus + Predicción + Scheduler │
        │   ├─ contexto + memoria (conversación viva, toda la sesión)│
        │   └─ máquina de estados                                    │
        └──────────────────────────────────────────────────────────┘
                         │  muestra / oculta / anima
                         ▼
              SomaOverlay (EFÍMERO: visible solo al invocar)
               ├─ SomaCharacter  (personaje + animaciones)
               ├─ Conversación   (voz + texto)
               └─ Atenuador + captador de clics (bloquea el ERP)
```

---

## 1. Auditoría de reutilización (obligatoria — resultado)

### 1.1 Se REUTILIZA
| Activo | Ubicación | Rol en SOMA |
|---|---|---|
| `SomaWorker` (wake-word "Ey SOMA" 20 idiomas + STT, QThread) | `src/utils/soma_worker.py` | **Escucha residente**; señales `soma_activado/comando_detectado/estado_cambiado/error_ocurrido` |
| `SomaTTS` (TTS neural persistente + fallback) | `src/utils/soma_tts.py` | **Voz de salida**; `decir/detener/confirmar_activacion` |
| Ciclo de vida SOMA (worker/thread/tts + shutdown) | `src/main.py` (`SmartManagerApp`) | Punto donde vive el **SomaKernel** (nivel app, sobre el `QStackedWidget`) |
| `CopilotService` (+ `contexto/memoria/acciones/intencion/respuestas/seguridad`) | `src/services/copilot/` | **Cerebro** conversacional |
| **`AgentManager` + `especialistas`** (`registrar/localizar(dominio)/delegar/coordinar`; 9 agentes) | `src/services/agentes/` | **Base del sistema de SKILLS** (cada dominio = una skill) |
| Event Bus | `src/services/eventos/` | **Observación** (proactividad) |
| Event Registry (UI) | `src/gui/foundation/events.py` | Contexto de pantalla (`PanelOpened`…) |
| Scheduler | `src/services/scheduler.py` | Chequeos proactivos periódicos (`registrar/registrar_job`) |
| PredictionService · Gemelo · Automatización · Gobierno · Simulador · Autonomía | `src/services/*` | Capacidades que las skills exponen |
| Foundation `tokens/permissions/icons/events` | `src/gui/foundation/` | Identidad visual + permisos del overlay |
| Navegación (`SmartManagerApp.abrir_ventana_por_id/manejar_apertura/cierre`) | `src/main.py`, `menu_principal.py` | **Acciones de navegación** de SOMA |
| `_SomaCancelFilter` (clic global cancela TTS) | `src/main.py` | Se integra en el captador de clics del overlay |

### 1.2 Se RECONFIGURA (resolver duplicidad)
- **Cerebro**: hoy los comandos pasan por `soma_engine.parsear_comando` + `soma_queries` (SQL directo).
  Se sustituye por **`CopilotService`** (que ya orquesta agentes/IA/servicios). `soma_engine` se conserva
  **solo** como *fast-path* de navegación (abrir/cerrar módulo) y fallback sin IA; `soma_queries` como
  fallback offline.
- **Skills**: NO se crea un registro nuevo — se **extiende `AgentManager`**. Cada módulo aporta su skill
  como un agente registrado por dominio (ver §11).
- **Botón `_SomaIndicator`** (píldora superior derecha): **se elimina** y lo sustituye el **personaje**
  como único punto de acceso permanente (ver §4). El estado (color) que hoy da la píldora pasa a
  reflejarse en el propio personaje.

### 1.3 Es NUEVO (imprescindible)
`SomaKernel`, `SomaOverlay`, `SomaCharacter` + controlador de animaciones, panel de conversación,
`SomaObserver` (proactividad), contrato de **Skill** (fino, sobre `AgentManager`), atenuador+captador
de clics.

---

## 2. Estructura de carpetas

Cerebro/servicio (sin Qt donde sea posible) separado de la UI (regla "no lógica en la GUI"):

```
src/soma/                     # CEREBRO / SERVICIO RESIDENTE
    __init__.py               # kernel() → singleton del SomaKernel
    kernel.py                 # SomaKernel: orquestador residente (worker+tts+cerebro+skills+observador+overlay)
    estado.py                 # Máquina de estados (9 estados) + señales
    contexto.py               # Contexto de sesión (usuario/empresa/tienda/almacén/módulo/pantalla/permisos/idioma/actividad) — reutiliza copilot.contexto
    memoria.py                # Memoria conversacional de sesión — reutiliza copilot.memoria
    voz.py                    # Adaptadores STT/TTS (envuelve SomaWorker+SomaTTS; enchufables)
    observador.py             # SomaObserver: escucha Event Bus + Predicción + Scheduler → auto-invocación
    skills/                   # SKILLS (finas; delegan en servicios/AgentManager)
        __init__.py           # registro/descubrimiento de skills
        base.py               # contrato SomaSkill (nombre, dominios, puede(intención), ejecutar(ctx))
        registro.py           # SkillRegistry (reutiliza/deriva de AgentManager)
        # skills nuevas donde no haya agente equivalente (correo, centro_inteligencia, gemelo, prediccion…)

src/gui/soma/                 # UI (Overlay + Personaje). Solo presentación.
    __init__.py
    overlay.py                # SomaOverlay: overlay app-level, atenúa el ERP y capta/bloquea clics
    personaje.py              # SomaCharacter: carga formato-agnóstica del personaje
    animaciones.py            # Controlador de animaciones (9 estados + microanimaciones)
    conversacion.py           # Panel de conversación (voz + texto)

# REUTILIZADOS sin mover: src/utils/soma_worker.py, src/utils/soma_tts.py,
#                         src/services/copilot/*, src/services/agentes/*, src/gui/foundation/*
```

---

## 3. Ciclo de vida del servicio (SomaKernel)

1. **Arranque** (tras login, reutilizando `_iniciar_soma` en `SmartManagerApp`): `kernel = soma.kernel()`
   toma el `SomaWorker` (escucha) y `SomaTTS` (voz) ya existentes, arranca el `SomaObserver`, crea el
   `SomaOverlay` **una sola vez** (oculto) como hijo de `SmartManagerApp`, resuelve el contexto y
   coloca el **personaje en reposo** (acceso permanente).
2. **Residencia**: el kernel vive toda la sesión. Escucha en 2º plano; memoria y contexto se mantienen.
3. **Invocación** (wake word o clic en el personaje → **mismo flujo**): estado `APARECIENDO` → atenúa el
   ERP + activa el captador de clics → `ESCUCHANDO` con la animación de "mano a la oreja".
4. **Conversación**: voz o texto → cerebro (CopilotService + skills) → respuesta (texto + TTS).
5. **Despedida**: timeout de silencio, comando de cierre o **clic fuera de SOMA** → `DESAPARECIENDO` →
   overlay oculto, ERP restaurado. **El kernel sigue vivo** (memoria intacta).
6. **Cierre**: `kernel.shutdown()` (reutiliza el shutdown actual de worker/tts).

---

## 4. Acceso permanente: el personaje sustituye al botón

- El **botón SOMA (superior derecha) desaparece**. El **personaje** es el **único** punto de acceso
  permanente (no habrá dos accesos).
- El personaje tiene **dos presentaciones del mismo asset** (no dos personajes):
  - **Reposo** (`Dormido`): presencia discreta y permanente (pequeña, semitransparente, con
    microanimaciones de "vivo"). Es el acceso permanente que reemplaza al botón.
  - **Activo**: al invocarse, el mismo personaje pasa al overlay (centrado abajo) con la experiencia
    completa (atenuación + conversación + animaciones).
- El **estado** de SOMA (escuchando/pensando/hablando/error) se refleja en el propio personaje (ya no
  en una píldora aparte).
- *Decisión a confirmar (§18):* posición de reposo del personaje (esquina donde estaba el botón vs.
  dock inferior-centro).

---

## 5. Invocación (dos caminos, un solo flujo)

- **Wake Word**: escucha continua en 2º plano (reutiliza `soma_worker.detectar_wake`, 20 idiomas). Al
  detectarla → invoca.
- **Clic en el personaje**: pulsar el personaje en reposo → invoca.
- Ambos llaman a **`SomaKernel.activar()`** → exactamente el mismo flujo interno (aparición + escucha).

---

## 6. Comportamiento del ERP mientras SOMA está activo

Requisito explícito (difiere de un overlay "tipo Siri" permisivo):

- El ERP permanece **completamente visible** pero **ligeramente atenuado** (capa oscura semitransparente)
  → deja claro que el foco es la conversación con SOMA.
- **El ERP NO es interactivable** mientras SOMA está activo: un **captador de clics** a pantalla completa
  (bajo el personaje/overlay) **intercepta TODOS los eventos de ratón** y **no los propaga** al ERP.
- **Primer clic fuera de SOMA** → única acción: **cancelar la conversación + ocultar SOMA + restaurar el
  ERP**. Nada más (no pulsa botones, no abre módulos, no ejecuta acciones). El clic **no llega** al ERP.
- Implementación (a validar): overlay a pantalla completa, hijo de `SmartManagerApp`, con
  `eventFilter`/`mousePressEvent` que consume el evento (`event.accept()`), atenuación por `QColor`
  semitransparente; el personaje y el panel de conversación quedan por encima y sí reciben interacción.
- **No modifica ningún layout** existente (es un hermano superpuesto; no se inserta en los layouts).

---

## 7. El personaje y sus animaciones

- **El personaje lo diseñas tú**; se integra tal cual (sin rediseñar/reinterpretar/generar otro). El
  sistema es **formato-agnóstico**: sprites PNG por animación (reproductor `QTimer`), GIF/APNG
  (`QMovie`), o PNG + transform (`QPropertyAnimation`); extensible a Lottie/Spine sin refactor.
- **Máquina de estados (mínimo 9)** — `estado.py` conduce, `animaciones.py` reproduce:
  `Dormido · Apareciendo · Escuchando · Pensando · Hablando · Esperando · Desapareciendo · Error ·
  Confirmación`.
- **Al aparecer**: `Apareciendo` (fade-in + leve subida) → **`Escuchando`: el personaje levanta la mano
  hacia la oreja** ("estoy escuchándote"). Encadenadas y fluidas.
- **Vivo en reposo/espera**: `Dormido`/`Esperando` **nunca inmóviles** → microanimaciones (respirar,
  parpadear, leve movimiento de cabeza). Se sentirá vivo.
- La GUI **no decide**: refleja el estado del kernel (`reproducir(estado)`).

---

## 8. Conversación (voz + texto) desde el overlay

- **Todo** ocurre en el overlay; **nunca** ventanas nuevas. El usuario **habla** (worker →
  `comando_detectado`) o **escribe** (input del overlay). Las respuestas aparecen en el mismo overlay.
- Pipeline: entrada → `SomaKernel.preguntar(texto)` → `CopilotService.preguntar_async(...)` (asíncrono,
  no bloquea la UI) → respuesta en el panel + `SomaTTS.decir(...)`.
- Multi-idioma heredado (i18n + traducción canónica ya usada por `_soma_on_comando`). Estilo visual por
  **Foundation tokens**; visibilidad por **permisos** (un OPERARIO ve menos que un ADMINISTRADOR).

---

## 9. Memoria (v1: solo sesión)

- Reutiliza `copilot.memoria` (historial por usuario, en proceso), **residente en el kernel** → la
  conversación **no se pierde** aunque el personaje desaparezca y se reinvoque minutos después.
- **v1: solo sesión** (no persistente). Persistencia en BD = ampliación futura.

---

## 10. Contexto (asistente contextual, no chatbot ciego)

`contexto.py` (sobre `copilot.contexto`) mantiene vivo: **usuario · empresa · tienda · almacén · módulo
activo · pantalla activa · permisos · idioma · actividad reciente**. El módulo/pantalla activos se
obtienen de `SmartManagerApp.currentWidget()`/`v_id` y de la suscripción a `PanelOpened` (Event
Registry). Así SOMA responde "en contexto" ("¿esto qué es?", "abre el stock de este artículo").

---

## 11. Sistema de SKILLS (orquestación, no un archivo gigante)

SOMA es un **orquestador**. Cada módulo aporta sus capacidades como una **Skill**. Se **reutiliza y
extiende `AgentManager`** (que ya es un registro de especialistas por dominio) — no se crea un sistema
paralelo.

- **Contrato `SomaSkill`** (`skills/base.py`), fino: `nombre`, `dominios`, `puede(intención, ctx)`,
  `ejecutar(consulta, ctx) → respuesta explicable`. Un adaptador permite que **cada `Agente` existente
  funcione como Skill** sin reescribirlo.
- **Registro/descubrimiento** (`skills/registro.py`): reutiliza `AgentManager.registrar/localizar`.
  Alta perezosa e idempotente (como hoy). Añadir una skill = registrar un agente por dominio, **sin
  tocar el orquestador** (escalable durante años).
- **Skills ya cubiertas por agentes existentes**: Comercial/CRM, Compras, Stock/Inventario,
  Tesorería/Financiero, RRHH, Fiscal, Logística, TPV, Auditoría.
- **Skills nuevas a añadir** (como agentes/skills donde no exista equivalente): Centro de Inteligencia,
  Correo, Gemelo Digital, Predicción, Workflow, Gobierno, Simulador, Autonomía.
- **Enrutado**: `CopilotService.preguntar` ya delega por dominio en `AgentManager` (y coordina varias
  con "¿qué debería hacer hoy?"). SOMA aprovecha ese enrutado; las skills solo **orquestan servicios
  existentes** (nunca reimplementan lógica).

---

## 12. Modo Observador (proactividad)

`SomaObserver` (`observador.py`) — SOMA observa aunque no esté visible, y se **auto-invoca** solo cuando
hay algo **realmente importante** (sin hablar continuamente):

- **Fuentes** (reutilizadas): Event Bus (eventos en tiempo real), PredictionService (roturas/impagos/
  riesgos), Automatización, Workflow, Auditoría, alertas del Gemelo; chequeos periódicos vía **Scheduler**.
- **Filtro/umbral**: solo eventos de prioridad alta/crítica; con **throttling** y "no molestar" para no
  ser invasivo. Reutiliza prioridades del Event Bus y niveles de riesgo de Predicción/Gemelo.
- **Auto-invocación**: al superar el umbral → `SomaKernel.activar(motivo=…)` → el personaje aparece y
  dice, p.ej., *"He detectado una posible rotura de stock dentro de dos días."* Con acción sugerida
  (que pasa por Gobierno/Workflow/Autonomía, nunca ejecución directa).
- La máquina de estados admite **disparo interno** (observador) además del wake word/clic.

---

## 13. Sistema de acciones

Reutiliza `copilot.acciones` (delega en AutomationService/Workflow/Gobierno/Autonomía respetando
permisos y aprobaciones) + el **puente de navegación** de `SmartManagerApp`. Regla heredada: **SOMA
propone**; las acciones críticas pasan por Gobierno + Workflow + Autonomía Supervisada (Enterprise 10).
SOMA **no** crea un canal de ejecución paralelo.

---

## 14. Comunicación con todos los módulos

Al vivir en `SmartManagerApp` (raíz), SOMA está disponible en **todos** los módulos con la misma
interfaz. **Observa** vía Event Bus + Event Registry; **actúa** vía skills (servicios) + navegación. Sin
acoplarse a la implementación interna de cada módulo.

---

## 15. Integración Foundation / Components / Shell / Event Bus / Registry / Seguridad

- **Foundation**: `tokens` (identidad visual del overlay), `icons`, `permissions` (visibilidad por
  rol/tenant), `events` (Event Registry). 
- **Components**: el panel de conversación usa estilos/tokens Enterprise para coherencia; el overlay
  **no** es una `QtEnterpriseWindow` (es un overlay transversal, no una pantalla de módulo).
- **Enterprise Shell**: SOMA no se aloja como pestaña; sí puede **abrir** hosts por navegación.
- **Event Bus / Registry**: observación de negocio + de UI (contexto/proactividad).
- **Seguridad/Roles**: toda respuesta/acción respeta RBAC + Gobierno (permisos visuales y de autoridad).

---

## 16. Componentes nuevos — resumen

| Componente | Tipo | Responsabilidad |
|---|---|---|
| `SomaKernel` | Servicio residente (singleton) | Orquesta worker+tts+cerebro+skills+observador+overlay; estado/contexto/memoria |
| `estado.py` | Máquina de estados | 9 estados + señales a personaje/eventos |
| `voz.py` | Adaptadores | Envuelve `SomaWorker`/`SomaTTS` (STT/TTS enchufables) |
| `observador.py` | Servicio | Proactividad (Event Bus + Predicción + Scheduler) |
| `skills/` | Orquestación | Contrato Skill + registro sobre `AgentManager` |
| `SomaOverlay` | UI | Overlay app-level: atenúa + capta/bloquea clics; muestra/oculta |
| `SomaCharacter` | UI | Personaje (formato-agnóstico) |
| `animaciones.py` | UI | 9 estados + microanimaciones |
| `conversacion.py` | UI | Voz + texto y render de respuestas |

Reutilizados: `SomaWorker`, `SomaTTS`, `CopilotService`, `AgentManager`+especialistas, Event Bus,
Event Registry, Scheduler, Predicción/Gemelo/Automatización/Gobierno/Autonomía, Foundation, navegación.

---

## 17. Escalabilidad futura

- **STT/TTS enchufables** (`voz.py`): Google/edge hoy; Whisper/Vosk offline o voces premium mañana.
- **Cerebro enchufable**: CopilotService ya delega en IA/estimadores sustituibles (LLM propio/API).
- **Skills sin límite**: nuevas capacidades = nuevos agentes/skills registrados, sin degradar la arquitectura.
- **Proactividad creciente**: nuevas fuentes de observación se suman al `SomaObserver`.
- **Personaje evolutivo**: formato-agnóstico.
- **Multi-superficie**: separación cerebro (`src/soma`) / UI (`src/gui/soma`) → futura versión web/móvil
  con el mismo kernel (mismo espíritu Base/Qt del Enterprise Shell).
- **Multiempresa/multitienda/multi-idioma**: heredados.

---

## 18. Decisiones (resueltas por el máster + pendientes de confirmar)

**Resueltas por tu especificación:**
- ERP mientras SOMA activo → **atenuado + NO interactivo + clic fuera = cancelar/ocultar** (clic no
  propaga). *(Antes lo había propuesto no-modal; queda anulado por tu regla.)*
- Acceso → **solo el personaje** (el botón desaparece); wake word **y** clic en el personaje, mismo flujo.
- Memoria → **solo sesión** en v1.
- Skills → **extender `AgentManager`** (no crear registro paralelo).

**Pendientes de confirmar antes de implementar:**
1. **Formato del personaje** (sprites PNG por animación / GIF-APNG / PNG+transform). El sistema será
   agnóstico, pero conviene fijar el principal según tu asset.
2. **Posición de reposo** del personaje (esquina superior derecha, donde estaba el botón, vs. dock
   inferior-centro).
3. **Cerebro v1**: ¿todo a CopilotService o **híbrido** (fast-path de navegación + CopilotService)?
   (Recomendado: híbrido por latencia.)
4. **Umbral de proactividad** v1: ¿qué prioridad mínima dispara la auto-invocación (solo CRÍTICA, o
   ALTA+CRÍTICA)?

---

## 19. Fuera de alcance

- Diseño del personaje (lo aportas tú). 
- Implementación (empieza solo tras aprobar este documento).
- Cambios en la implementación UI Enterprise (queda intacta).

---

*Documento de arquitectura para revisión. No se ha escrito ni modificado código de SOMA.*
