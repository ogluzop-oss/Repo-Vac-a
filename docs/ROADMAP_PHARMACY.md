# Roadmap oficial — Mejora de la edición PHARMACY

> **Cómo usar este documento:** cuando el usuario diga "es hora de mejorar la versión Pharmacy",
> lee este roadmap completo, confirma la fase a abordar, presenta un plan concreto (ficheros a
> tocar/crear, migración si aplica, tests) y **espera aprobación** antes de implementar. Prioriza
> las fases **sin bloqueo externo** (1, 2-núcleo, 5, 6, 7, 9).

## Contexto

Smart Manager tiene una edición **Pharmacy** (gateada por `src/services/verticales.py` con funciones
`pharmacy.*`). Ya existen:

- Módulo **Recetas** (`gui/recetas_gui.py`, `services/recetas.py`, migr `0185_recetas`): la farmacia
  **registra** la receta emitida por un médico → **dispensa** → salida de stock por el motor **oficial**
  (`db/salida_stock.salida_stock_oficial` → kárdex + FEFO + lotes). El farmacéutico **no** prescribe.
- La base retail: TPV, catálogo, lotes/caducidad, compras, contabilidad, tesorería, RBAC, auditoría, cifrado.

El objetivo de este roadmap es convertir la edición Pharmacy en un sistema de gestión de farmacia **real y
conforme a la normativa del sector**, por fases.

## Reglas permanentes (obligatorias en TODAS las fases)

1. **N7 — cero duplicación:** reutilizar los motores existentes. El stock **SIEMPRE** sale por el motor
   oficial (`db/salida_stock.salida_stock_oficial` → kárdex + FEFO + lotes). Prohibido crear un motor de
   stock, de venta o de documento paralelo.
2. **Gating por FUNCIÓN, no edición nueva:** cada capacidad se expone con `verticales.visible("pharmacy.<x>")`
   y se activa solo donde corresponde. Ningún módulo se elimina; se gatea.
3. **La GUI SOLO orquesta;** toda la lógica vive en `services/` (y `db/` para acceso a datos). Migraciones
   versionadas en `src/database/migraciones` (registrar el nombre en `__init__.py`).
4. **HONESTIDAD (crítico):** las piezas con **bloqueo EXTERNO** (credenciales/API de sanidad, SEVEM/EMVO,
   lectores hardware, sensores) se construyen como **adaptadores DEGRADABLES** y se marcan "preparado/roadmap".
   **NUNCA** presentar un mock como funcional ni simular respuestas oficiales (misma política que Fiscal/AEAT
   y ESL: sin credenciales de producción, no se acepta/transmite).
5. **Datos sanitarios = máxima protección:** cifrado (`utils/cripto`), RBAC (`services/autorizacion`),
   auditoría (`log_auditoria`) e historial de accesos. Sin secretos en claro ni en logs.
6. **Cierre de cada fase:** suite unitaria completa verde + verificación por render offscreen de la UI +
   actualización de `docs/MODULOS_POR_EDICION.md`.

## Fases

### FASE 1 — Catálogo dual EAN + Código Nacional (C.N.) · *sin bloqueo externo*
Soporte del **Código Nacional** del medicamento junto al **EAN** de parafarmacia; búsqueda y alta por ambos;
distinción producto **OTC/parafarmacia** vs **medicamento con receta (Rx)**.

### FASE 2 — Dispensación con copago · *núcleo sin bloqueo; lector de tarjeta sanitaria = externo*
Tipo de **aportación** del paciente (nivel de renta/cobertura), **cálculo automático del copago** (importe
del usuario) vs **importe financiado** (Administración/mutua), y **bloqueo de dispensación no autorizada**.
La lectura de tarjeta sanitaria y la validación en tiempo real quedan como **adaptador degradable** (externo).

### FASE 3 — Integración de Receta Electrónica · **BLOQUEO EXTERNO: API/Web Services de sanidad**
Adaptador **degradable** para validar prescriptores, descargar historial de dispensación y facturar
electrónicamente. Sin credenciales → no se acepta/transmite (no se simula).

### FASE 4 — Trazabilidad SEVEM/EMVO (Datamatrix) · **BLOQUEO EXTERNO: credenciales SEVEM + lector**
Lectura y validación del **código único (Datamatrix)** por caja y **"desactivación"** al dispensar. Adaptador
degradable; sin conexión oficial no se marca como verificado.

### FASE 5 — Stock avanzado y caducidades · *sin bloqueo externo*
Alertas automáticas por **lote/caducidad** (FEFO ya existe en el motor), **devoluciones al almacén mayorista**
e inventario específico de medicamentos.

### FASE 6 — Liquidación mensual de recetas · *sin bloqueo externo*
Cierre mensual que agrupa las dispensaciones con receta (**copago cobrado** vs **importe financiado**) para
facturar al **colegio farmacéutico / servicio de salud / mutuas**.

### FASE 7 — Estupefacientes y psicotrópicos · *sin bloqueo externo*
**Libro contable regulado** con concordancia exacta **stock físico ↔ recetas dispensadas**, para auditoría de
las autoridades sanitarias.

### FASE 8 — Cadena de frío y GDPR · *núcleo sin bloqueo; sensores = externo*
Marcado de artículos **2–8 °C** con alertas; refuerzo **GDPR/LOPD** (cifrado de datos de salud, perfiles
jerárquicos, historial de accesos). Integración de sensores = adaptador externo.

### FASE 9 — TPV multifunción farmacia + parafarmacia · *sin bloqueo externo*
Cobro en una sola transacción de **venta libre + línea de copago de Rx**, pasarelas de pago y fidelización,
reutilizando el TPV existente.

## Resumen de bloqueos

| Fase | Capacidad | Bloqueo externo |
|---|---|:--:|
| 1 | Catálogo dual EAN + C.N. | — |
| 2 | Copago / aportación (núcleo) | — (lector tarjeta sí) |
| 3 | Receta electrónica (API sanidad) | **Sí** |
| 4 | Datamatrix / SEVEM-EMVO | **Sí** |
| 5 | Stock avanzado + caducidades | — |
| 6 | Liquidación mensual de recetas | — |
| 7 | Libro de estupefacientes | — |
| 8 | Cadena de frío + GDPR (núcleo) | — (sensores sí) |
| 9 | TPV multifunción | — |

---

*Fuente de intención: brief del sector farmacéutico del usuario. La implementación real debe respetar las
Reglas permanentes de arriba y la arquitectura congelada del proyecto (`CLAUDE.md`).*
