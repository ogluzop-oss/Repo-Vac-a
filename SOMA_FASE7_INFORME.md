# SOMA · FASE 7 — Autonomía Empresarial Supervisada (Director de Operaciones Digital)

**Estado:** IMPLEMENTADA Y VERIFICADA · LOCAL, sin commitear · No se inicia la Fase 8 hasta aprobación.

SOMA deja de ser solo reactivo: **detecta situaciones, genera objetivos de negocio razonados y
propone iniciativas priorizadas ANTES de que el usuario pregunte** — pero **nunca ejecuta nada por su
cuenta**. Toda ejecución sigue pasando por **Workflow, Gobierno y Autonomía Supervisada**. SOMA
propone, observa, razona, prioriza y explica; jamás sustituye al usuario ni decide estados (el
`SomaKernel` sigue siendo la única fuente de verdad). Todo el trabajo es de fondo, sin bloquear
UI/overlay/voz/animaciones.

---

## 1. Arquitectura general (paquete `src/soma/direccion/`)

Nuevo paquete de **dirección de operaciones**, capa fina que **reutiliza** los motores existentes sin
duplicarlos:

```
src/soma/direccion/
  __init__.py       Fachada: analizar() · generar_y_priorizar() · explicar()
  temporal.py       Contexto temporal (franja/día/fin de semana/periodo)
  riesgos.py        Risk Engine  (reutiliza razonamiento Fase 4)
  oportunidades.py  Opportunity Engine (Predicción/Gemelo/temporal)
  objetivos.py      Autonomous Goal Engine (deriva de riesgos+oportunidades)
  iniciativas.py    Initiative Generator (une, prioriza, explica, aprende)
  bandeja.py        Bandeja de sesión (inbox consultable)
  historial.py      Historial + aprendizaje de decisiones (persistencia)
```

Dirección de dependencias: `temporal → {riesgos, oportunidades} → objetivos → iniciativas → fachada`.
`bandeja` e `historial` son transversales. **No se ha creado ningún motor paralelo**: los riesgos
reutilizan el `razonamiento` de la Fase 4 (que ya interpreta Predicción/Gemelo/Workflow/Auditoría/
KPIs); los objetivos y oportunidades se apoyan en `PredictionService`, el Gemelo Digital y el contexto
temporal; las iniciativas se vinculan a **plantillas de misión ya existentes** (Fase 6).

## 2. Sistema de Objetivos Autónomos (`objetivos.py`)

`generar(riesgos, oportunidades, id_empresa)` **no aplica reglas aisladas**: agrega las señales
(riesgos + oportunidades) por dominio, se queda con la **peor prioridad** de cada grupo (`P.peor`) y
las mapea a objetivos de negocio (`_GRUPOS`: inventario, compras, liquidez, ventas, procesos, control
interno). Cada objetivo queda **razonado** (por qué) y, cuando procede, vinculado a una misión
(`reducir_costes` / `mejorar_ventas`). Verificado: **2 objetivos** derivados en el entorno de prueba.

## 3. Motor de Detección de Oportunidades (`oportunidades.py`)

Detecta **oportunidades, no solo problemas**, priorizadas y best-effort (si una fuente falta, se omite
sin romper):
- **Clientes que podrían volver** — inactivos ≥ 3 vía `prediccion.servicio().clientes()` (CRM).
- **Liberar inmovilizado** — sobrestock ≥ 5 artículos vía `ia.adaptadores.articulos_exceso()`.
- **Campaña recomendable** — por temporada (navidad/rebajas) usando el contexto temporal.

Cada oportunidad lleva prioridad, por qué, datos, consecuencias, especialistas y misión sugerida.

## 4. Motor de Riesgos Empresariales (`riesgos.py`)

Estructura cada hallazgo del `razonamiento` (Fase 4) en un riesgo con **nivel · probabilidad ·
impacto · causas · consecuencias · acciones · especialistas**. No crea un segundo detector: enriquece
el existente. Verificado: **9 riesgos** estructurados en el entorno de prueba.

## 5. Generador de Iniciativas (`iniciativas.py`)

`generar()` combina riesgos + oportunidades + objetivos en una lista **priorizada, deduplicada
(por clave) y totalmente explicable**: añade el campo **`si_no_hago_nada`** ("¿qué pasa si no hago
nada?") y garantiza `especialistas`/`acciones`. Aplica el **aprendizaje** de prioridades por tipo.
`explicar(ini)` produce la justificación completa (por qué + datos + especialistas + consecuencias +
qué pasa si no se actúa). **Solo propone; nunca ejecuta.**

## 6. Priorización inteligente

Se reutiliza `src/soma/prioridad.py` (MUY_BAJA/BAJA/MEDIA/ALTA/CRÍTICA). Las iniciativas se ordenan
por `P.nivel` descendente y **solo CRÍTICA/ALTA** (`P.merece_intervencion`) justifican una
auto-invocación proactiva; el resto queda en la **bandeja** para consulta. Verificado: lista ordenada
descendente y `top` que merece intervención.

## 7. Bandeja de oportunidades (`bandeja.py`)

Inbox de sesión (singleton `bandeja()`). El observador **vuelca todas** las iniciativas y el usuario
consulta bajo demanda: *"¿qué has detectado hoy?"*, *"muéstrame oportunidades"*, *"¿hay riesgos?"*,
*"¿qué me recomiendas hoy?"*. Dedup por clave con cooldown (1800 s), `listar(tipo, limite)`,
`resumen()` → {total, riesgos, oportunidades, objetivos}. Verificado: resumen `{total:8, riesgos:5,
oportunidades:1, objetivos:2}`.

## 8. Historial de recomendaciones + aprendizaje (`historial.py` · migración 0099)

Persiste en la tabla **`soma_recomendaciones`** (migración **0099**, aditiva/reversible): qué recomendó
SOMA, cuándo, por qué, tipo, prioridad, estado (PROPUESTA/ACEPTADA/RECHAZADA) y resultado.
`ajuste_prioridad(tipo)` implementa un **aprendizaje lento** (solo prioridades, nunca la personalidad):
con < 3 decisiones no ajusta; si se acepta un tipo con frecuencia sube (+1), si se rechaza baja (−1).
`aplicar_ajuste()` mueve la prioridad dentro de la escala. Verificado: registro/decisión persistidos y
ajustes coherentes (`ALTA +1 → CRÍTICA`, `MEDIA −1 → BAJA`).

## 9. Personalidad empresarial y contexto temporal (`temporal.py`)

`momento()` deriva franja (inicio/mediodía/tarde/cierre), día, fin de semana y periodo (navidad/
rebajas/fiscal/normal). `saludo()` y `matiz()` dan naturalidad de **compañero de trabajo, no chatbot**
("Ya que se acerca el cierre…", "En periodo de rebajas…"). Se usa tanto en las oportunidades como en
las respuestas de la bandeja. La personalidad de fondo sigue siendo la de fases previas (no se
duplica).

## 10. Integración con el SomaKernel y el Observador

- **`observador.py`** (`_analizar_bg`): en vez de solo `razonamiento.recopilar()`, ahora llama a
  `direccion.generar_y_priorizar()` (que reutiliza el razonamiento por dentro), **rellena la bandeja**
  y devuelve la iniciativa que merece intervención. Mantiene el filtro de cooldown/no-repetir y el
  fallback al razonamiento puro si el paquete no estuviera.
- **`kernel.py`**:
  - `procesar()`: nuevo paso **0e** que enruta las consultas de bandeja a `_responder_bandeja()`
    (lista natural + tabla visual + contexto temporal).
  - `intervenir()`: registra la recomendación en el **historial** (base del aprendizaje) y, si la
    iniciativa tiene misión asociada, **ofrece prepararla** (`_ofrecer_mision` → estado colaborativo
    `_esperando`), sin ejecutar.
  - `_responder_colaboracion()`: nuevo caso `iniciativa` — si el usuario acepta, registra
    **ACEPTADA** y **crea una misión** (Fase 6); si rechaza, registra **RECHAZADA** y la deja en la
    bandeja. Reutiliza el Mission Engine sin tocarlo (mapa de frase canónica →
    `plantillas.detectar`).
  - `_explicar_hallazgo()`: añade la explicabilidad **"¿qué pasa si no hago nada?"**.

## 11. Integración con el Mission Engine y los Especialistas IA

Una iniciativa aceptada se convierte en **misión** (`MissionEngine.crear/iniciar`, Fase 6) que
coordina los **Especialistas IA** (AgentManager) en paralelo y consolida una única respuesta. **La
Fase 6 no se modifica**: se reutiliza mapeando la clave de misión (`mejorar_ventas`/`reducir_costes`)
a su frase canónica, detectada por `plantillas.detectar`. Las tareas críticas de la misión siguen
exigiendo **aprobación** (Autonomía/Workflow) antes de ejecutarse.

## 12. Garantía de gobierno (nunca ejecuta lo crítico)

SOMA **propone, observa, razona, prioriza y explica**. No modifica datos, no aprueba tareas ni
sustituye al usuario. Toda ejecución pasa por Workflow + Gobierno + Autonomía Supervisada. El paquete
`direccion/` **no escribe** en ninguna tabla operativa: solo persiste su propio historial
(`soma_recomendaciones`). La creación de una misión hereda las salvaguardas de la Fase 6.

## 13. Rendimiento (todo en segundo plano)

El análisis de dirección corre en el hilo daemon del observador (throttle por eventos, latido ~90 s a
través del Scheduler existente). Los resultados vuelven al hilo principal por señal Qt
(`hallazgo_listo`). No se bloquea la UI, el overlay, la voz ni las animaciones.

## 14. Verificaciones realizadas

| Verificación | Resultado |
|---|---|
| AST de todos los ficheros nuevos/editados | **AST OK** |
| Migración 0099 aplicada (DB de prueba) | `aplicadas: ['0099']` · tabla `soma_recomendaciones` existe |
| Engines: riesgos/oportunidades/objetivos | 9 / 1 / 2 detectados |
| Iniciativas priorizadas + dedup | 8 (de 12 señales) · **orden desc correcto** |
| Solo CRÍTICA/ALTA auto-invocan | top merece intervención = **True** |
| Bandeja + resumen | `{total:8, riesgos:5, oportunidades:1, objetivos:2}` |
| Explicabilidad "si no hago nada" | presente + `explicar()` completo |
| Historial + aprendizaje (persistencia) | registro/decisión OK · `ALTA+1→CRÍTICA`, `MEDIA−1→BAJA` |
| Kernel: detección de consultas de bandeja | 4/4 frases detectadas, negativo descartado |
| Kernel: oferta de misión (colaboración) | `_esperando` fijado · iniciativa sin misión no bloquea |
| Reutiliza Fase 6 sin tocarla | `plantillas.detectar` reconoce las frases canónicas |
| Smoke test | **5 passed** |
| Enterprise UI (foundation/components/paneles) | intacta (untracked `??`) |
| Fases SOMA previas | intactas (`src/soma/` local, sin commitear) |

---

## Recomendación para la Fase 8 (no iniciar hasta aprobación)

No un bloque funcional nuevo, sino **madurez**: (a) **memoria a largo plazo** de la relación
usuario↔SOMA (preferencias, temas recurrentes, tono) sobre la persistencia ya existente;
(b) **reanudación de misiones** tras reinicio (rehidratar el Mission Engine desde su tabla);
(c) refinamiento de **UX/personalidad** (más naturalidad conversacional, matices por contexto);
(d) **multimodal** (voz+overlay+animaciones más ricas ya cableadas); (e) **optimización de
producción** (perfilado del trabajo de fondo, límites de recursos). Todo aditivo y reutilizando la
arquitectura consolidada.
