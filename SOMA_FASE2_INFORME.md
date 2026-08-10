# SOMA — COPILOTO IA · INFORME TÉCNICO FASE 2 (Experiencia visual)

Fase dedicada **exclusivamente** a la experiencia de usuario: personaje, overlay, animaciones,
microanimaciones, atenuación, captador de clics y panel conversacional. **Sin** inteligencia
conversacional ni comportamiento proactivo (fases posteriores). Todo se apoya en el `SomaKernel` de
Fase 1 (no modificado). Plan UI Enterprise **intacto**.

> **Assets del personaje**: el Character Pack (10 ilustraciones + parpadeo) lo aportas tú. El sistema
> es agnóstico al formato y funciona ya con **placeholders**; al dejar tus PNG en `assets/soma/` con
> los nombres del manifiesto (`assets/soma/README.md`), el personaje real aparece sin tocar código.

---

## 1. Componentes creados

`src/gui/soma/` (solo presentación; refleja el estado del kernel):

| Archivo | Responsabilidad |
|---|---|
| `character_pack.py` | Carga **agnóstica al formato** (PNG · sprite sheet · GIF/APNG) + placeholder; mapa estado→ilustración; parpadeo |
| `personaje.py` | `SomaCharacter` (`QGraphicsView`): muestra la ilustración y aplica transformaciones (escala/rotación/desplazamiento/opacidad) |
| `animaciones.py` | `ControladorAnimacion`: acentos por estado + **microanimaciones** + secuencias de aparición/desaparición |
| `conversacion.py` | `SomaConversationPanel`: panel definitivo (historial + entrada de texto + micrófono) |
| `overlay.py` | `SomaOverlay`: overlay a nivel de app (reposo/activo), atenuación, captador de clics, posicionamiento |
| `__init__.py` | `instalar_overlay(app)` — crea el overlay **una sola vez** y lo conecta al kernel |

`assets/soma/README.md` — manifiesto del Character Pack (nombres y prioridades de formato).

Cambios **aditivos** (no alteran comportamiento existente):
- `src/main.py`: instala el overlay tras el kernel (`QTimer` → `instalar_overlay(self)`).
- `src/gui/menu_principal.py`: **oculta la píldora SOMA** (`_soma_indicator.setVisible(False)`) — el
  botón se sustituye por el personaje (§1 del encargo). Se conserva el objeto para no romper
  `soma_set_estado` (actualiza un widget oculto, sin efecto visual).

---

## 2. Integración con SomaKernel

- El overlay **implementa el contrato `EspacioConversacional`** y se registra con
  `kernel.set_espacio(self)`; el kernel lo usa para `mostrar/ocultar/mostrar_estado/mostrar_respuesta`.
- El overlay **se suscribe a la máquina de estados** (`kernel.maquina.suscribir`) y, en cada cambio,
  llama a `ControladorAnimacion.aplicar_estado(nuevo)`. **La GUI jamás decide estados**: solo los
  representa (verificado con los 9 estados).
- **Invocación** (clic en el personaje en reposo) → `kernel.activar()` → el kernel transiciona
  (`APARECIENDO→ESCUCHANDO`) y llama a `espacio.mostrar()`. Mismo flujo previsto para la wake word.
- **Cancelación** (clic fuera en activo) → `kernel.ocultar()` → `DESAPARECIENDO→DORMIDO` +
  `espacio.ocultar()`. El cerebro (memoria/contexto) permanece vivo.

---

## 3. Arquitectura definitiva del Overlay

Hijo de `SmartManagerApp` (raíz), transparente y **desacoplado del ERP** (no modifica ningún layout).
Dos modos:

- **REPOSO**: el overlay ocupa **solo** un dock pequeño (abajo-centro, 108 px) con el personaje; el
  resto del ERP es **plenamente interactivo**. Pulsar el personaje **invoca** a SOMA.
- **ACTIVO**: el overlay cubre **toda** la app → **atenúa** el ERP (capa negra semitransparente,
  α=120) y lo deja **no interactivo**; el personaje se sitúa **centrado-abajo** y aparece el panel
  conversacional encima. Reposiciona automáticamente al redimensionar la app (`eventFilter` sobre el
  padre — sin tocar el padre).

Disponible desde **cualquier módulo** (CRM, RRHH, Tesorería, Workflow, Centro de Inteligencia…) con la
misma interfaz, por vivir a nivel de app.

---

## 4. Sistema de carga del Character Pack

`character_pack.py` resuelve `estado → ilustración` y carga por **prioridad de formato**:
`*.gif/*.apng` (QMovie) → `*.sheet.png`+`*.json` (sprite) → `*.png` (estático) → **placeholder**
dibujado. Todo tras `RecursoPersonaje.pixmap()`/`avanzar()`, de modo que el resto del sistema
(transformaciones, microanimaciones) es **idéntico sea cual sea el formato**. Caché por clave.
Mapa `ESTADO_A_ILUSTRACION` con alternativas (p.ej. `PENSANDO→pensando→procesando`).

---

## 5. Sistema de animaciones

Combina **cambio de ilustración** (por estado del kernel) con **transformaciones** suaves:
- Secuencia de **aparición** (§9): fundido + elevación (+46 px→0) con ligero overshoot de escala; al
  terminar, el kernel deja el estado en `ESCUCHANDO` (mano a la oreja). Fluida (~460 ms, OutCubic).
- Secuencia de **desaparición**: fundido + leve descenso; al terminar, vuelve a reposo.
- **Acentos por estado**: rebote (Confirmación/Hablando), sacudida (Error), inclinación (Pensando).
- Estilo Disney/Pixar: amplitudes **sutiles**, nunca exageradas.

---

## 6. Sistema de microanimaciones

Continuas mientras SOMA está visible (nunca imagen estática):
- **Respiración**: oscilación de escala (±2 %).
- **Balanceo**: rotación suave (±1,4°).
- **Flotación**: bob vertical (±4 px).
- **Parpadeo**: superposición periódica (2,8–5,2 s aleatorio) de `parpadeo.png` (120 ms).
Todo a ~30 fps con un único `QTimer` (barato) + fases sinusoidales. Verificado activo en reposo y en
uso.

---

## 7. Gestión del captador de clics

- En **activo**, el overlay cubre toda la app: por z-order, **todos** los eventos de ratón llegan al
  overlay (el ERP debajo no los recibe).
- `mousePressEvent`: si el clic cae sobre el personaje o el panel → se acepta y no hace nada; si cae
  **fuera** → **cancela** (`kernel.ocultar()`) y **consume** el evento (`event.accept()`). El clic
  **jamás** se propaga al ERP, no pulsa botones ni abre módulos.
- En **reposo**, el overlay solo cubre el dock → clic = invocar; el resto del ERP funciona normal.

---

## 8. Verificaciones realizadas

| Verificación exigida | Resultado |
|---|---|
| SOMA funciona desde cualquier módulo | ✅ overlay a nivel de app (raíz), disponible en todo el ERP |
| El Overlay nunca modifica layouts | ✅ hijo superpuesto; `eventFilter` reposiciona sin tocar el padre |
| ERP correctamente atenuado | ✅ capa α=120 solo en activo (validado por captura) |
| El captador de clics consume completamente | ✅ clic fuera → `accept()`=True, cancela, no propaga |
| El personaje representa todos los estados | ✅ **los 9 estados** mapean a su ilustración |
| Microanimaciones continuas | ✅ respiración/balanceo/flotación/parpadeo activos |
| Character Pack se carga correctamente | ✅ con placeholder si faltan assets; PNG/GIF/sprite soportados |
| Transformaciones independientes del formato | ✅ todo tras `RecursoPersonaje` (mismo pipeline) |
| Overlay solo se crea una vez por sesión | ✅ `instalar_overlay` idempotente (singleton) |
| Sin fugas de memoria | ✅ animaciones con `DeleteWhenStopped`; overlay único; sin ciclos |
| Sin regresiones sobre el ERP | ✅ **smoke `5 passed`** |
| Plan UI Enterprise intacto | ✅ `git status`: solo `main.py`/`menu_principal.py` aditivos + `gui/soma` y `assets/soma` nuevos |
| Kernel Fase 1 intacto | ✅ `src/soma/` sin cambios |

Validación visual (captura offscreen): ERP atenuado + personaje centrado-abajo + panel conversacional
flotante (cabecera SOMA, burbujas, entrada+micro+enviar). Texto en cajas = falta de fuentes en
headless (no es bug). Personaje = placeholder hasta colocar los PNG reales.

---

## 9. Posibles mejoras para la Fase 3

- **Wake word → overlay**: conectar (de forma aditiva) `SomaWorker.soma_activado` a `kernel.activar()`
  para que la voz muestre el overlay (marshaling al hilo principal).
- **Inteligencia conversacional**: enrutar el texto/voz del panel a `CopilotService` (cerebro) +
  Especialistas IA; hoy el panel es la interfaz definitiva sin IA.
- **Estados conversacionales reales**: que el kernel conduzca `ESCUCHANDO→PENSANDO→HABLANDO` durante
  una respuesta real.
- **Personalidad**: comenzar a poblar `src/soma/personality/` (tono/expresiones) para modular texto y
  gestos.
- **Modo observador/proactivo**: umbral sobre Event Bus/Predicción/Scheduler para auto-invocación.
- **Transición personaje reposo↔activo**: si se desea, animar el traslado del dock al centro (hoy son
  el mismo personaje en dos disposiciones, ya coherente).

---

## Estado

**Fase 2 completada y verificada.** La experiencia visual está lista y conectada al kernel; solo
faltan tus ilustraciones reales en `assets/soma/` (el sistema ya las integra sin cambios). No se
inicia ninguna fase posterior hasta tu revisión y aprobación.
