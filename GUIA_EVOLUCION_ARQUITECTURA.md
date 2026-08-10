# GUIA_EVOLUCION_ARQUITECTURA.md — Reglas de evolución + patrón Strangler

Fecha 2026-07-30. Guía OFICIAL para futuras fases: cómo crear/ubicar/nombrar módulos, qué dependencias pueden
tener y qué patrón seguir. Incluye el **mecanismo Strangler documentado** (Objetivo 6). Solo documentación.

## 1. Reglas para crear módulos nuevos

- **Ubicación**:
  - Lógica de dominio → `src/services/<dominio>/` (o dentro del dominio propietario existente; ver
    ARQUITECTURA_DOMINIOS.md).
  - Acceso a datos → `src/db/<dominio>.py`.
  - UI escritorio → `src/gui/` con `QtEnterpriseWindow`/`QtEnterprisePanel` + `gui/components`.
  - REST → un **router** en `src/api/routers/<x>.py` (delegando en `services/`), registrado en
    `routers/__init__.py`. **No** crear un backend paralelo.
  - Back Office web → dentro de `src/portal_web/`.
- **Nombre**: único y NO colisionante. Antes de nombrar `catalogo`/`portal`/`scheduler`/`stock`/`cloud`/`ia`,
  consultar el glosario y elegir un nombre que exprese la jerarquía (p. ej. `ia.decisiones`, no otro
  `inteligencia`). **Declarar el módulo nuevo en ARQUITECTURA_DOMINIOS.md.**
- **Dependencias**: respetar FRONTERAS_CAPAS.md (services no importa gui; api solo services; núcleo sin
  dominios). Preferir **fachadas** y **composición** sobre reimplementar (N7).
- **Patrón**: aditivo, degradable, multi-tenant (`id_empresa`/`id_tienda` del token/contexto, nunca por
  dominio), auditable, sin secretos en claro (Secret Manager).

## 2. Qué NO crear

- Segundos motores (forecasting/Event Bus/Storage/Auth/Scheduler/predicción/licenciamiento) → reutilizar.
- APIs duplicadas → consumir las existentes; endpoint nuevo solo si es imprescindible.
- `if plan == "PRO"` disperso → usar `saas.entitlements`.
- Nuevas fuentes de stock/precio/marca → usar `articulos`/`web_config`.

## 3. Mecanismo Strangler (sustitución progresiva SIN romper compatibilidad)

Objetivo: poder sustituir una GUI/módulo monolítico por otro nuevo de forma gradual, conservando
`v_id`/rutas/firmas públicas. **No se implementa ninguna sustitución ahora**; este es el procedimiento oficial.

### 3.1 Para pantallas GUI (menú por `v_id`)
El enrutado del menú (`gui/menu_principal.abrir_ventana_por_id`) ya usa **lazy loading** por `v_id`. El
Strangler se aplica así, sin infra nueva:

1. Crear la **nueva** pantalla (`QtEnterpriseWindow`/panel + `gui/components`) en un módulo aparte.
2. En el punto de enrutado del `v_id`, conmutar a la nueva implementación **conservando el mismo `v_id`** (un
   flag/registro de conmutación por pantalla permite volver atrás al instante).
3. Marcar la implementación antigua `@deprecated` (docstring + aviso), **manteniéndola** un ciclo.
4. Eliminar la antigua **solo cuando no queden referencias** (imports/rutas/callbacks).
5. Tests offscreen en cada paso → **0 regresiones**.

> Ejemplo real ya iniciado: Canal Web — la nueva entrada `gui/canal_web_gui.py` (WEB-02) sustituye
> progresivamente al `_CanalWebConfigDialog` embebido en `tpv.py`; la extracción física se completará por este
> mecanismo cuando el ecosistema pueda reorganizarse sin riesgo.

### 3.2 Para servicios/módulos
1. Crear el nuevo servicio con la **misma firma pública** (o una fachada que la conserve).
2. Redirigir los consumidores al nuevo por fachada/alias (`from x import y as y_legacy`).
3. Marcar el antiguo `@deprecated`; retirar cuando fan-in = 0.

### 3.3 Reglas de compatibilidad (invariantes)
- Conservar `v_id`, rutas REST (`/api/v1/...`), y firmas públicas.
- Nunca romper imports existentes → usar **alias** durante la transición.
- Cada paso: suite completa verde.

## 4. Convenciones de nomenclatura (para evitar la deuda actual)

- Un concepto = un nombre. Los "layers" del mismo concepto van como **submódulos de un paquete paraguas**
  (`catalogo/pim`, `catalogo/serializacion`, `catalogo/comercial`) en vez de módulos homónimos dispersos.
- Prefijos claros de dominio; evitar homónimos entre `db/`, `services/`, `gui/`.
- Documentar TODO módulo nuevo en `ARQUITECTURA_DOMINIOS.md` (fuente única de verdad de responsabilidades).

## 5. Checklist para futuras fases de simplificación

- [ ] ¿El cambio conserva contratos públicos (`v_id`/rutas/firmas)?
- [ ] ¿Se hace por Strangler (nuevo + deprecación, sin big-bang)?
- [ ] ¿Respeta FRONTERAS_CAPAS.md?
- [ ] ¿Está declarado/actualizado en ARQUITECTURA_DOMINIOS.md?
- [ ] ¿Suite completa verde (0 regresiones)?
- [ ] ¿Sin secretos, multi-tenant intacto, N7?

---
**Documentos relacionados**: ARQUITECTURA_DOMINIOS.md · MAPA_DEPENDENCIAS.md · GUI_MONOLITOS.md ·
CANDIDATOS_FUSION.md · FRONTERAS_CAPAS.md · AUDITORIA_MAESTRA_ARQUITECTURA.md.
