# AUDITORÍA PREVIA — ENTITLEMENTS (Fase 16)

Fecha 2026-07-29. Auditoría del sistema de licenciamiento actual ANTES de implementar. Evolución, no reescritura.

## 1. Arquitectura actual de licenciamiento

`src/services/saas/`: `licensing.py` (resolver + enforcement), `planes.py` (catálogo), `enforcement.py`
(gate menú/backend), `suscripciones.py`, `metricas.py`, `dunning.py`, `branding.py`, `multiempresa.py`,
`aislamiento.py`, `backup_tenant.py`. Persistencia: `empresa_licencia` (plan por empresa), `planes_saas`/
`modulos_saas`/`plan_modulos`, `historico_licencias`, `eventos_licencia` (migr 0059).

## 2. Resolver central existente

`licensing.py`: `licencia_activa(id_empresa)`, `estado_operativo`, `modulo_habilitado(modulo)`,
`limite_disponible(recurso)` (`{limite,usado,disponible,ok}`), `validar_operacion(modulo=,recurso=)` (lanza
`LicenciaError`), `_contar(tabla,id_empresa)`. `enforcement.py`: `nivel_acceso`, `exigir_modulo`,
`acceso_modulo(v_id)`.

## 3-6. Planes / módulos / límites existentes

`planes.py.PLANES`: **BASIC** (8 módulos base; usuarios 3/tiendas 1/almacenes 1/correos 3), **PLUS** (base +
RRHH/tesorería/contab/BI/AEAT/forecasting…; 50/10/20/25), **PRO** (todos los módulos; 9999 = ilimitado de
facto). Límites en `planes_saas` + código.

## 7. Puntos de enforcement actuales

- Backend: `validar_operacion` / `enforcement.exigir_modulo` (por MÓDULO).
- Menú/GUI: `enforcement.acceso_modulo(v_id)` (mapa `MODULO_POR_VID`).
- Legacy: sin licencia → **todo permitido** (comportamiento actual intacto).

## 8-9. Comprobaciones duplicadas / gating disperso

- **0 `if plan == "PRO"/"BASIC"/"PLUS"`** dispersos (confirmado por grep). No hay anti-patrón que deshacer.
- No hay duplicación de lógica de límites: se centraliza en `limite_disponible`.

## 10. Cambios necesarios (evolución, N7)

1. **Conflicto de semántica de planes**: hoy **PRO** es el tier superior (9999) y **PLUS** el intermedio. La
   Fase 16 exige **PLUS = ilimitado/total** y PRO = profesional. → El nuevo modelo de **capabilities** adopta la
   semántica Fase 16 (PLUS top). El catálogo de MÓDULOS de `planes.py` se conserva para compatibilidad; el
   nuevo `entitlements` es la fuente de verdad de **capacidades avanzadas y cuotas** (capa distinta de módulos).
2. Nuevo módulo `services/saas/entitlements.py`: matriz central BASIC/PRO/PLUS de capabilities (booleans) y
   límites (cuotas), resolver `has/can/limit/require/estado_cuota/puede_crear/plan_actual`, PLUS = todo
   true/ilimitado, legacy = sin restricción, multi-tenant por `id_empresa`, auditoría de denegaciones,
   estado `OVER_LIMIT` (downgrade no destructivo).
3. Compatibilidad: añadir wrappers `licensing.capability_habilitada`/`estado_cuota` y extender
   `validar_operacion(..., capability=)` — sin romper `modulo_habilitado`/`limite_disponible`.

## 11. Compatibilidad con la arquitectura actual

- Reutiliza `licencia_activa`/`_contar`/`LicenciaError` (N7, sin motor paralelo).
- **0 tablas nuevas** (matriz en código; licencia en `empresa_licencia`).
- APIs antiguas intactas → sin migración destructiva.

## 12. Riesgos de regresión

- **Bajo**: legacy (sin licencia) = ilimitado → las empresas/tests sin plan asignado no cambian de
  comportamiento. Las funcionalidades no se re-escriben (sección 18); el enforcement por capability es
  **opt-in** vía `validar_operacion(capability=)`/`require()`. Sin cambios en TPV/Stock/Caja/CRM/RRHH/etc.
- Semántica PLUS↔PRO: el nuevo modelo de capabilities es independiente del catálogo de módulos legacy; no se
  altera `planes.py` para no romper `modulo_habilitado`.

## Conclusión

Se procede a **evolucionar** (no reescribir): nuevo `entitlements.py` como fuente única de capacidades/cuotas,
con PLUS ilimitado, reutilizando el resolver de licencias existente y preservando las APIs actuales.
