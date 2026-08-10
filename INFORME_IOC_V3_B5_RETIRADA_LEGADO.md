# IOC v3 — BLOQUE V: Retirada controlada del legado (informe técnico final)

> Ejecución del plan de retirada (Fases L1-L4) diseñado en el Bloque IV. Estrategia Strangler
> **completamente reversible**, sin regresiones. **No** se modificó lógica funcional, GUI, SQL,
> modelos, permisos, auditoría ni estructura de BD. **Sin migraciones. Sin commits.**

## Resumen

| Acción | Resultado |
|--------|-----------|
| Seams de la **capa de datos** delegados en la fachada `db.identidad_contexto` | **23/24** (96 %) |
| Seams **funcionales** de servicio restantes migrados (CRM variantes + contratos) | **4** (→ 90/90 funcionales) |
| `gemelo.fuentes.emp` | **DEPRECADO** (shim de compatibilidad, comportamiento intacto) |
| Adaptador nuevo `identidad_contratos` (homogéneo, factory) | creado |
| Smoke | **5 passed** · Regresiones: **0** |

## Elementos eliminados (lógica duplicada consolidada)

**Ningún fichero ni función se ha borrado físicamente** (los helpers `_emp`/`_empresa` siguen
referenciados por miles de llamadas; eliminarlos exigiría reescribir todos los call-sites → fuera de
alcance y arriesgado). Lo que se ha **eliminado es la lógica de resolución duplicada**: los cuerpos de
los helpers ya no reimplementan la resolución, sino que **delegan** en un único punto:
- **Capa de datos (23 ficheros):** `_emp`/`_empresa` → `db.identidad_contexto.empresa_id` (db → db).
- **Capa de servicios funcional (4 ficheros):** `crm/{campanias,objetivos,rutas}`, `contratos_pro`
  → `identidad_<mod>.empresa_id`.

## Elementos deprecados

- **`gemelo.fuentes.emp`:** marcado `[DEPRECATED — IOC v3]` con docstring técnico y referencia a IOC.
  Se conserva como **shim**: toda llamada sigue devolviendo exactamente el mismo valor. No se emite
  `DeprecationWarning` en runtime (para no alterar el comportamiento observable). Retirada definitiva
  prevista en Fase L4, cuando no queden usos primarios.

## Elementos conservados (deliberadamente)

- **`EMPRESA_DEFAULT_ID`** — semilla multiempresa (constante base). **No se retira.**
- **`db.empresa.*`** (`empresa_actual_id`, `tienda_actual_id`, …) — resolución canónica sobre la que
  se construye IOC y la fachada de datos. **Se mantiene** (es el fundamento, no legado duplicado).
- **`ref_tienda`/`ref_almacen`** — feature «Asignar referencia» (compatibilidad Strangler).
- **Helpers `_emp`/`_empresa`** — se mantienen como **delegadores finos** (no se borran; siguen siendo
  el punto de llamada de cada módulo).
- **IOC completo** (v1/v2, IdentityAPI, adaptadores, fachada).

## Rollback

- **Reversible al 100 %:** cada helper migrado conserva su *fallback* original exacto en el `except`;
  revertir = restaurar el cuerpo anterior del helper (marca `IOC v3 (Bloque V)` localizable).
- **Sin cambios de BD** → rollback inmediato por control de versiones; sin datos que revertir.
- La fachada `db.identidad_contexto` por defecto es idéntica a lo canónico (sin resolver inyectado).

## Riesgos

| Riesgo | Estado / mitigación |
|--------|---------------------|
| Cambio de comportamiento en capa de datos | Nulo: `db.identidad_contexto` = canónico por defecto; verificado `==` en 23 módulos |
| Ciclo de importación (db ↔ fachada) | Evitado: imports perezosos dentro de los helpers; db → db |
| `fuentes.emp` deprecado rompe usos | Nulo: shim con comportamiento idéntico |
| GUI aún usa `empresa_actual_id` | Diferido (L5) para no arriesgar la GUI sin cobertura de tests; ver «pendientes» |
| Infra/Enterprise sin migrar | Bajo valor/negocio; documentado como L2 opcional |

## Porcentaje de legado eliminado / restante

- **Capa de datos:** **96 %** de seams delegados en la fachada (23/24; 1 helper sin parámetro no
  canónico).
- **Servicios funcionales de negocio:** **100 %** (90/90) enrutados por IOC.
- **Seams de servicio totales:** 90/175 ≈ **51 %** (el 49 % restante es **infra/Enterprise**, no
  módulos de negocio).
- **GUI:** 0 % (33 ficheros con `empresa_actual_id`, diferido a L5).
- **`fuentes.emp`:** deprecado (uso primario en funcionales ≈ 0; permanece como *fallback*/shim).

## Métricas antes / después

| Métrica | Antes (fin Bloque IV) | Después (Bloque V) |
|---------|----------------------|--------------------|
| Seams de servicio migrados | 86 | **90** |
| Seams de datos migrados a fachada | 0 | **23** |
| `fuentes.emp` | mecanismo activo | **deprecado (shim)** |
| Adaptadores de identidad | 16 | **17** (+contratos) |
| Fuentes de verdad de identidad | dispersa (2-4 formas) | **unificada (IdentityAPI + fachada db)** |

## Impacto en rendimiento

- **Neutro.** El camino caliente (`empresa_id`) sigue resolviendo con `db.empresa` (una llamada), sin
  eventos ni E/S adicional. La fachada añade una indirección de función (coste despreciable). La caché
  de IOC solo interviene en resoluciones significativas (no en `_emp`). Sin regresión de latencia.

## Impacto en mantenimiento

- **Positivo.** La resolución de identidad queda **unificada**: un punto por capa
  (`identidad_<mod>.empresa_id` en servicios, `db.identidad_contexto.empresa_id` en datos). Se elimina
  la reimplementación duplicada (2-4 formas) y se centraliza la evolución futura. La deprecación
  documentada guía a los desarrolladores hacia IOC.

## Compatibilidad

- IOC v1/v2, IdentityAPI, IdentityContext, fachada DB, multiempresa/multitienda, Event Bus, caché,
  telemetría, Scheduler y RBAC: **verificados y sin cambios**.
- Todos los módulos funcionan **exactamente igual** (comportamiento `==` verificado). **Smoke: 5
  passed. Regresiones: 0.**

## Pasos pendientes antes de IOC v3 definitivo

1. **L2 (opcional):** homogeneizar los ~85 seams de **infra/Enterprise** (bi_corp, distribucion,
   resiliencia, actividad, gobierno, autonomia, saas, …) con adaptadores factory.
2. **L3 (resto capa datos):** migrar `db/stock.py::_empresa()` (sin parámetro) y los helpers de
   empresa+tienda (kardex/lotes/mermas) a la fachada, caso a caso con pruebas.
3. **L4:** sustituir los usos primarios restantes de `fuentes.emp` por `empresa_id` y **retirar** el
   shim cuando el contador llegue a 0.
4. **L5 (GUI):** migrar los 33 ficheros de `gui/*` que llaman `empresa_actual_id` a `IdentityAPI`/
   adaptador (con evidencia visual, al no haber tests de GUI).
5. **Opcional:** exportador Prometheus/OpenTelemetry real; refactor de los 4 adaptadores standalone
   (crm/stock/compras/produccion) al factory; activar ranura de versión **v3** en la IdentityAPI.

## Conclusión

El legado de identidad queda **reducido al mínimo imprescindible en las capas de datos y de servicios
de negocio**, con la resolución **unificada alrededor de IdentityAPI y de la fachada de datos**, de
forma **completamente reversible y sin una sola regresión**. El sistema queda preparado para la fase
final de IOC v3 estable (retirada del shim, GUI e infra), con un plan claro (L2-L5) y rollback
garantizado.

### Anexo — Cambios de este bloque
- Migrados (delegación): 23 ficheros `db/*` → `db.identidad_contexto`; 4 servicios funcionales
  (crm campanias/objetivos/rutas, contratos_pro).
- Deprecado: `services/gemelo/fuentes.py::emp` (shim, comportamiento intacto).
- Nuevo: `services/contratos/identidad_contratos.py` (adaptador homogéneo).
- Sin cambios de BD, lógica, SQL, modelos, GUI, permisos ni auditoría.
