# SOMA — COPILOTO IA · INFORME TÉCNICO FASE 5 (Inteligencia operativa, memoria persistente y colaboración)

Objetivo: que SOMA **empiece a trabajar** (copiloto operativo): mantener contexto largo, colaborar,
abordar tareas complejas y responder con más calidad de razonamiento. Todo **reutilizando** la
arquitectura F1–F4 (congelada) y la infraestructura Enterprise; sin motores/razonadores/memorias/
contextos paralelos. Async, en segundo plano, sin bloquear la UI. Plan UI Enterprise **intacto**.

---

## 1. Componentes añadidos (solo `src/soma/` + migración + panel visual)

| Archivo | Rol |
|---|---|
| `memoria_persistente.py` | Aprendizaje LENTO: preferencias, hábitos, módulos/dominios frecuentes (contadores) |
| `memoria_trabajo.py` | Memoria de TRABAJO de sesión (tema/módulo/actividad) → "continuemos donde lo dejamos" |
| `tareas.py` | Tareas LARGAS en 2º plano (progreso, sin bloquear) + handlers (ventas/pedidos/proveedores) |
| `planificador.py` | Peticiones complejas → plan + confirmación; reutiliza Simulador/Autonomía |
| `razonador.py` | Razonamiento MULTIPASO (varias fuentes → una síntesis) vía AgentManager/Gemelo/Predicción |
| `database/migraciones/0097_soma_memoria.py` | Tabla `soma_memoria` (persistencia útil) |
| `gui/soma/conversacion.py` (ext.) | Respuestas VISUALES (tabla/KPIs/lista/cronología Enterprise) + referencias |

Extensiones del **SomaKernel** (F5): enrutado operativo en `procesar`, `_responder_resultado`
unificado, colaboración/continuidad/tareas, aprendizaje en navegación/consulta. **F5 no modificó
`main.py`.**

## 2. Arquitectura ampliada

`procesar(texto)` enruta, por orden: explicabilidad (F4) → **colaboración** (si esperaba respuesta) →
**continuidad** ("continuemos…") → fast-path navegación → **planificación** (petición compleja) →
**tarea larga** → **razonamiento multipaso / CopilotService**. Toda respuesta pasa por
`_responder_resultado` (personalidad + texto + **visual** + **referencias** + voz). El trabajo pesado
corre en **hilos daemon** y vuelve al hilo principal por señales Qt (puente del cerebro + señales del
gestor de tareas). No bloquea la UI.

## 3. Sistema de memoria persistente

Tabla `soma_memoria` (migr 0097): `usuario/tipo/clave/valor/contador`. **Aprende lentamente** por
frecuencia (`registrar_uso` → contador; `frecuentes` devuelve hábitos que superan el umbral). Guarda
SOLO lo útil (módulos/dominios frecuentes, preferencias como formato de export, idioma…), **nunca
conversaciones**. No duplica la memoria de sesión (`copilot.memoria`): la complementa. `perfil(usuario)`
da la foto aprendida para el contexto. Verificado: tras 4 aperturas, "tesorería" pasa a frecuente;
preferencia "excel" recordada.

## 4. Gestión de memoria de trabajo

`MemoriaTrabajo` (sesión): tema/módulo/actividad reciente, actualizada al navegar y al conversar.
`retomar()` reconstruye el hilo ("Seguimos donde lo dejamos: el inventario. Lo último fue…") sin
volver a explicar el contexto. Verificado.

## 5. Sistema de planificación

`planificador.py`: intenciones complejas reconocidas (abrir tienda / mejorar ventas / reducir costes)
→ **plan por pasos** + petición de confirmación (no responde de golpe). Al confirmar, **reutiliza el
Simulador** (impacto what-if VIRTUAL) y deja el terreno para la **Autonomía Supervisada** (ejecución
gobernada). Verificado: propone plan → espera "sí" → simula impacto con KPIs.

## 6. Motor de colaboración

Estado de diálogo `_esperando` en el kernel: cuando SOMA hace una pregunta (p.ej. confirmar un plan),
la siguiente respuesta del usuario se interpreta (sí/no/ambiguo → re-pregunta). Conversación natural,
no monolítica: **analiza → propone → espera → continúa**.

## 7. Razonamiento multipaso

`razonador.sintetizar`: para consultas amplias ("resumen de cómo va la empresa", "análisis…"), SOMA
consulta INTERNAMENTE **Gemelo Digital + Especialistas IA (AgentManager.coordinar) + PredictionService**
y **sintetiza una única respuesta** con referencias. El usuario nunca ve el proceso interno.
Verificado: respuesta sintetizada con fuentes.

## 8. Respuestas visuales

El panel de conversación (dentro del **overlay**, sin ventanas nuevas) renderiza **componentes
Enterprise**: `EnterpriseTable` (tablas), `EnterpriseCard`/`EnterpriseDashboardGrid` (KPIs),
`EnterpriseTimeline` (cronologías), listas, y **referencias** (`EnterpriseStatusBadge` con las
fuentes). El resultado del cerebro/razonador/tareas/planificador puede traer `visual` + `fuentes`.
Verificado: tarea larga devuelve tabla; plan devuelve KPIs; multipaso muestra fuentes.

## 9. Aprendizaje implementado

- **Módulos**: cada apertura registra un hábito (`registrar_uso("modulo", vid)`) → módulos frecuentes.
- **Dominios**: cada consulta registra el dominio → dominios frecuentes.
- **Preferencias**: configuraciones explícitas (`aprender`). Con el tiempo, `perfil(usuario)` permite
  anticiparse **sin ser invasivo** (se usará desde el observador/contexto). Aprendizaje lento por
  umbral de frecuencia.

## 10. Referencias y continuidad

- **Referencias**: cada respuesta con datos del ERP muestra sus fuentes (Ventas/CRM/Tesorería/…),
  para transmitir confianza (no para justificar).
- **Continuidad**: la memoria de trabajo mantiene el hilo durante la sesión (horas); la persistente
  recupera preferencias entre sesiones.

---

## Verificaciones realizadas

| Verificación | Resultado |
|---|---|
| Memoria persistente funcionando | ✅ frecuentes/preferencia/perfil (tabla `soma_memoria`) |
| Memoria de trabajo funcionando | ✅ resumen/retomar |
| Recuperación automática de contexto | ✅ "continuemos donde lo dejamos" |
| Planificación multipaso | ✅ plan + confirmación + simulación |
| Colaboración natural | ✅ pregunta→espera→continúa (sí/no/ambiguo) |
| Respuestas visuales | ✅ tabla/KPIs/fuentes en el overlay |
| Razonamiento con Especialistas IA | ✅ síntesis multi-fuente (AgentManager/Gemelo/Predicción) |
| Rendimiento estable (no bloquea) | ✅ hilos daemon + señales Qt |
| Sin fugas de memoria | ✅ hilos efímeros; señales; overlay/gestor únicos |
| Sin regresiones | ✅ **smoke `5 passed`** |
| Compatibilidad F1–F4 | ✅ arquitectura congelada; solo extensiones aditivas |
| Plan UI Enterprise intacto | ✅ `git status`: solo SOMA + migración; F5 sin cambios en `main.py` |

---

## Mejoras previstas para la siguiente fase

Alineado con tu sugerencia: la siguiente gran evolución es un **Sistema de Agentes Autónomos**, donde
SOMA no solo aconseje sino que **coordine equipos de Especialistas IA** que colaboren entre sí para
resolver objetivos complejos (reorganizar un almacén, preparar una campaña, planificar una apertura),
siempre bajo Workflow/Gobierno/Autonomía Supervisada. Base ya lista: AgentManager (coordinación),
planificador (descomposición), tareas largas (ejecución en 2º plano), Simulador (impacto) y Autonomía
(ejecución gobernada). Otras mejoras: razonamiento con tendencias % reales, aprendizaje adaptativo de
preferencias (bajar prioridad de avisos ignorados), y persistencia de la memoria de trabajo.

---

## Estado

**Fase 5 completada y verificada.** SOMA mantiene contexto largo (memoria de trabajo + persistente),
colabora (plan + confirmación), aborda tareas largas en segundo plano, razona en multipaso y responde
con tablas/KPIs/referencias dentro del overlay — reutilizando toda la arquitectura existente, sin
bloquear la UI y sin ejecutar acciones críticas por su cuenta. No se inicia ninguna fase posterior
hasta tu revisión y aprobación.
