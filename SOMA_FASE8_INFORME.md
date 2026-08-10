# SOMA · FASE 8 — Madurez total del Copiloto IA

**Memoria empresarial · Personalidad viva · Continuidad · Experiencia premium**

**Estado:** IMPLEMENTADA Y VERIFICADA · LOCAL, sin commitear · Última gran evolución de SOMA.

La Fase 8 **no añade módulos ni motores nuevos**: transforma a SOMA en un compañero de trabajo que el
usuario percibe como alguien que trabaja con él todos los días — con **continuidad, memoria,
personalidad, presencia y madurez**. Todo se construye **ampliando** lo existente, nunca
sustituyéndolo.

---

## 0. Regla de oro cumplida: motores intactos

**No se ha modificado ninguno** de los componentes que el máster marcó como intocables:
`SomaKernel · Overlay · Mission Engine · Especialistas IA · Observador · Bandeja · Workflow ·
Gobierno · Autonomía`. Verificado: en esta fase solo se editaron `src/soma/razonador.py` (ampliación
aditiva, no es motor restringido) y `src/main.py` (capa de integración de la app), más ficheros
**nuevos**. La integración se hace **reutilizando caminos públicos ya existentes**:

- El **saludo de continuidad** se emite por el camino proactivo existente `kernel.intervenir(hallazgo)`.
- El **aprendizaje de hábitos** usa el **Scheduler** existente (job `soma_habitos`).
- Las **consultas históricas** entran por el flujo existente `kernel.procesar → razonador`.
- Las **respuestas multimodales** usan solo los tipos de `visual` que el overlay **ya sabe renderizar**.

## 1. Componentes ampliados (paquete nuevo `src/soma/empresa/`)

```
src/soma/empresa/
  __init__.py       Fachada + enganche al_iniciar_sesion(kernel)  [aditivo, desde main.py]
  conocimiento.py   Memoria empresarial a largo plazo  (tabla soma_empresa_conocimiento, migr 0100)
  habitos.py        Aprendizaje lento de hábitos (sin configuración manual)
  continuidad.py    Continuidad entre días (frase de retomar + contexto)
  reanudacion.py    Reanudación de misiones pendientes (SOLO lectura sobre Fase 6)
  clima.py          Personalidad adaptativa (clima de trabajo, profesional)
  historico.py      Contexto histórico (reutiliza BI KPIs serie_historica)
  multimodal.py     Respuestas multimodales (tipos que el overlay ya renderiza)
```

## 2. Sistema de memoria empresarial (`conocimiento.py` + migración 0100)

Nueva capa **por EMPRESA** (distinta de la memoria de sesión y de la memoria por usuario de la
Fase 5). Guarda **solo conocimiento útil, nunca conversaciones**: `decision · preferencia · habito ·
patron · config · iniciativa · objetivo`. Aprendizaje **lento** (contador de refuerzos, umbral 3) y
**reversible** (`olvidar()` → `activo=0`, nunca invasivo). API: `recordar / saber / consolidado /
resumen / frase / olvidar`. Ejemplos reales que puede recordar: *"La empresa revisa inventario los
lunes"*, *"Siempre exportan en Excel"*, *"Los martes son los de más actividad"*. Verificado: refuerzo
de contador (1→2), consulta por tipo, resumen agrupado, olvido reversible.

## 3. Sistema de continuidad (`continuidad.py` + `clima.py`)

Al volver, SOMA transmite que **no ha olvidado el trabajo**: `resumen_dia()` combina misiones
pendientes + conocimiento de la empresa; `saludo_continuidad()` construye un hallazgo (*"Buenos días.
Ayer dejamos en marcha «…», ahora esperando aprobación. ¿Lo retomamos?"* / *"Continúo exactamente
donde lo dejamos"*) que se emite por `kernel.intervenir`. **Nunca inventa recuerdos**: todo procede de
datos persistidos. Si no hay nada relevante, **no molesta** (devuelve None). Verificado: saludo
"Retomamos donde lo dejamos" generado a partir de misiones reales.

## 4. Reanudación de misiones (`reanudacion.py`)

Si una misión quedó **esperando aprobación / proveedor / RRHH / auditoría** (estados
`ESPERANDO_APROBACION · PAUSADA · EN_CURSO`), SOMA la **recupera, no crea una nueva**. Lee la misión
persistida (Fase 6: `soma_misiones` / `soma_mision_tareas`) conservando **historial, especialistas y
progreso**, y la surfacea para continuarla. **Solo lectura**: no modifica el Mission Engine ni ejecuta;
la ejecución crítica sigue pasando por Workflow/Gobierno/Autonomía. Verificado: 2 misiones pendientes
recuperadas con su resumen natural.

## 5. Personalidad adaptativa (`clima.py`)

Profesional, **nunca infantil, nunca finge emociones**: adapta un matiz según el **clima** del día —
`carga` ("Hoy tienes bastante carga; intentaré ayudarte todo lo posible"), `buenas_noticias` ("las
previsiones han mejorado respecto a antes"), `estable` ("Todo está bastante estable hoy"). Derivado de
la bandeja (nº de asuntos CRÍTICA/ALTA) y de la tendencia histórica. Se usa en los mensajes de
continuidad. No modifica la personalidad de la Fase 3: la complementa. Verificado: nivel `estable`.

## 6. Contexto histórico (`historico.py`)

Ante *"¿cómo evolucionó esto?"* SOMA responde con **histórico**, no solo con el dato actual. Mapea el
tema (ventas/stock/mermas/clientes/tesorería/compras) a KPIs y **reutiliza `services.bi.kpis.
serie_historica`** (no recalcula ni crea almacén nuevo): devuelve actual/anterior/variación/tendencia
+ serie, y lo presenta con visual multimodal. Integrado **sin tocar el kernel**: `razonador.es_analitica`
reconoce las consultas históricas y `razonador.sintetizar` responde con `historico` cuando procede.
Verificado: enrutado correcto y respuesta best-effort.

## 7. Respuestas multimodales (`multimodal.py`)

Amplía las visualizaciones (gráficos sencillos, comparativas, líneas temporales, evolución mensual,
tendencias) **sin abrir ventanas nuevas y sin tocar el overlay**: produce `visual` en los tipos que el
panel conversacional **ya renderiza** con componentes Enterprise (`tabla · kpis · timeline · lista`).
Un gráfico sencillo se representa como **sparkline Unicode** (`▁▂▃▄▅▆▇█`) en el texto + línea temporal
Enterprise. Verificado: `evolucion→timeline`, `tendencia→kpis`, `comparativa→tabla`, todos ⊆ tipos
soportados por el overlay.

## 8. Explicabilidad completa

Se mantiene la explicabilidad total de las Fases 4/7 (por qué · en qué datos me baso · consecuencias ·
qué pasa si no hago nada), y cada iniciativa/hallazgo lleva sus **especialistas** en el registro
(consultables vía `direccion.explicar`). Las respuestas históricas citan su fuente ("Histórico BI").
Nunca caja negra. No fue necesario modificar el kernel para ello.

## 9. Adaptación a cada empresa (`habitos.py`)

Aprendizaje **lento, sin configuración manual y reversible**: `observar()` deriva de datos reales cómo
trabaja la empresa (módulos frecuentes, formato de exportación, iniciativas que suele aceptar,
objetivos que completa, día de más actividad) y lo consolida en la memoria empresarial. Se ejecuta una
vez al iniciar sesión (en segundo plano) y a diario vía el **Scheduler existente** (job `soma_habitos`,
24 h). Verificado: 2 hábitos observados y persistidos.

## 10. Optimización general

Revisión de SOMA con criterio de **mínimo riesgo** (no se cambia el comportamiento de ningún motor):
- **Sin ventanas nuevas**: todo el multimodal reutiliza el renderer existente del overlay.
- **Reutilización estricta**: histórico → BI KPIs; reanudación → tablas de misiones; hábitos →
  memoria/​recomendaciones/misiones ya existentes. No se añade ninguna consulta pesada nueva en el
  arranque (el aprendizaje corre en hilo daemon y en el Scheduler, no bloquea).
- **Lazy imports** deliberados dentro de funciones para no alargar el arranque ni crear ciclos.
- **Sin fugas**: la bandeja y el conocimiento son best-effort y acotados (`LIMIT`, umbrales,
  cooldowns). El saludo se emite una sola vez por sesión (`_saludado`).
- Redundancia identificada y **conscientemente conservada**: el pequeño helper `_emp()` se repite por
  módulo para mantenerlos desacoplados; unificarlo acoplaría paquetes por una micro-optimización sin
  ganancia real. No se toca para no introducir riesgo.

## 11. Preparación para el futuro (solo arquitectura, no implementado)

El paquete `empresa/` deja el terreno preparado, sin implementarlo:
- **Asistentes con personalidad propia** — `clima.py` aísla el "carácter adaptativo"; añadir perfiles
  de personalidad es sumar módulos hermanos.
- **Varios copilotos simultáneos / agentes distribuidos** — la memoria es por empresa y las
  capacidades son módulos tras una fachada; el `SomaKernel` sigue siendo la única fuente de verdad.
- **Coordinación entre empresas** — `soma_empresa_conocimiento` está indexada por `id_empresa`.
- **Asistentes móviles / realidad aumentada** — la lógica vive en `services/`+`soma/` (sin Qt de
  presentación), lista para otra capa de interfaz.

## 12. Compatibilidad con todas las fases anteriores

| Fase | Estado |
|---|---|
| 1 Núcleo · 2 Visual · 3 Cerebro · 4 Proactivo | intactas |
| 5 Operativo · 6 Misiones · 7 Autonomía supervisada | intactas |
| Plan **UI Enterprise** (foundation/components/paneles/inteligencia) | **intacto** (untracked `??`) |
| Motores restringidos (kernel/overlay/mission/especialistas/observador/bandeja/workflow/gobierno/autonomía) | **sin editar** |

## 13. Pruebas realizadas

| Prueba | Resultado |
|---|---|
| AST de los 12 ficheros nuevos/editados | **OK** |
| Migración 0100 aplicada (DB de prueba) | `aplicadas: ['0100']` · tabla creada |
| Memoria persistente entre días (refuerzo/olvido reversible) | contador 1→2 · olvido OK |
| Aprendizaje lento de hábitos | 2 hábitos observados y persistidos |
| Reanudación de misiones (recupera, no crea) | 2 pendientes con historial/progreso |
| Recuperación del contexto / continuidad conversacional | saludo "Retomamos donde lo dejamos" |
| Comparación histórica | `es_historica` OK · `sintetizar` devuelve dict |
| Personalidad adaptativa | clima `estable` con matiz |
| Respuestas multimodales | tipos ⊆ {tabla,kpis,timeline,lista} · sparkline OK |
| Enrutado sin tocar kernel (procesar→razonador) | histórica → razonador OK |
| Saludo por camino proactivo (`kernel.intervenir`) | hallazgo bien formado, no rompe |
| Job `soma_habitos` en el Scheduler | registrado |
| Smoke test | **5 passed** |
| Sin regresiones · motores y UI Enterprise intactos | confirmado |

## 14. Recomendaciones futuras

- **Perfiles de personalidad** seleccionables por empresa (sobre `clima.py`), manteniendo el tono
  profesional.
- **Reanudación activa** de misiones (rehidratar la misión persistida en el Mission Engine) cuando se
  decida evolucionar la Fase 6 — hoy se surfacea en modo lectura para no tocar el motor.
- **Serie histórica ampliada**: poblar más KPIs en `bi_kpi_valores` para enriquecer `historico.py`.
- **Coordinación multiempresa / multicopiloto** aprovechando que la memoria ya es por `id_empresa`.
- **Métricas de uso del propio SOMA** (aceptación de recomendaciones, misiones completadas) como KPI
  interno de madurez.

---

**Fase 8 cerrada.** SOMA queda como un copiloto maduro: recuerda cómo trabaja la empresa, mantiene la
continuidad entre días, retoma lo pendiente, adapta su tono con profesionalidad y responde con
histórico y visualizaciones — todo **ampliando** la arquitectura existente, sin tocar ningún motor ni
la UI Enterprise.
