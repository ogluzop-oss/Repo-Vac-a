# IOC v2.0 — BLOQUE III (FINAL): Adopción de IOC en todos los módulos funcionales

> Cierre del Bloque III. Integra IOC como fuente única de identidad en los módulos funcionales
> restantes, siguiendo el patrón validado (CRM/Stock/Compras/Producción). Aditivo, behavior-preserving,
> multiempresa, auditado. **Sin migraciones, sin tablas.** Verificado; smoke 5 passed; cero regresiones.

## 1. Resumen global

- **16 adaptadores** de identidad homogéneos (`identidad_<mod>.py`): 4 previos (crm, stock, compras,
  produccion) + 12 nuevos (tpv, facturacion, logistica, rrhh, finanzas, calidad, sat, gmao, documental,
  fiscal, contabilidad, tesoreria).
- **1 factory único** `src/services/identidad/adaptador.py` — base homogénea que elimina duplicación:
  todos los adaptadores nuevos se construyen con `construir("<modulo>")`.
- **67 seams `_emp`/`_empresa` migrados** en 13 paquetes funcionales (además de los de los 4 bloques
  previos).

## 2. Seams migrados por módulo (capa servicio)

| Módulo | Paquete | Seams migrados | Adaptador |
|--------|---------|----------------|-----------|
| TPV | `services/tpv` | 2 | `identidad_tpv` |
| Ventas/Facturación | `services/facturacion` | 7 | `identidad_facturacion` |
| Logística | `services/logistica` | 1 | `identidad_logistica` |
| RRHH | `services/rrhh` | 2 | `identidad_rrhh` |
| Finanzas | `services/finanzas` | 9 | `identidad_finanzas` |
| Calidad | `services/calidad` | 7 | `identidad_calidad` |
| SAT | `services/sat` | 7 | `identidad_sat` |
| GMAO/Mantenimiento | `services/gmao` | 5 | `identidad_gmao` |
| Documentación | `services/documental` | 1 | `identidad_documental` |
| Fiscalidad (AEAT) | `services/aeat` | 8 | `identidad_fiscal` |
| Fiscalidad (Facturae/certif.) | `services/fiscal` | 4 | `identidad_fiscal` |
| Contabilidad | `services/contabilidad` | 8 | `identidad_contabilidad` |
| Tesorería | `services/tesoreria` | 6 | `identidad_tesoreria` |

Cada `_emp`/`_empresa` delega ahora en `identidad_<mod>.empresa_id(id_empresa)` conservando **su
fallback original exacto** (`fuentes.emp`, `id_empresa or empresa_actual_id()` o `EMPRESA_DEFAULT_ID`
según el módulo) → comportamiento idéntico garantizado (verificado `== fuentes.emp`).

## 3. Seams pendientes (documentados, justificados)

- **`services/sync_transport/` (5 ficheros):** infraestructura de sincronización/transporte de
  paquetes de datos (replicación), **no un módulo funcional de negocio**; forma de `_emp` no canónica.
- **`services/fiscal/evidencias.py::_empresa_de(registro)`:** **no es un seam canónico** — deriva la
  empresa de un *registro* (dict), no de `id_empresa`. Migrarlo cambiaría su semántica; se deja intacto.
- **Seams de capa datos** (`src/db/*` de Stock/Compras y otros): permanecen por la regla de no invertir
  `db → services`; ya usan las funciones canónicas `db.empresa` que IOC reutiliza (misma fuente de
  verdad). Se envolverán en el borde de servicio en una fase posterior.
- **Paquetes de infraestructura/Enterprise** (actividad, automatizacion, autonomia, bi_corp,
  distribucion, dr, resiliencia, saas, gobierno, seguridad, workflow, copilot, ia, simulador,
  prediccion, gemelo, bi): **fuera del alcance** de este bloque (no son módulos funcionales de negocio);
  auditables en una iteración futura si se desea homogeneizarlos.

## 4. Adaptador homogéneo (factory)

`src/services/identidad/adaptador.py` expone `construir(modulo)` → objeto con la interfaz común:
`empresa_id` (camino caliente, sin eventos, *fallback*), `tienda_actual`, `almacen_actual`,
`empresa_tienda_almacen`, `contexto` (IdentityContext), `identidad(ref_entidad, ref_id, …)`
(resolución significativa que publica `<modulo>.identidad.resuelta`) y `telemetria` (contadores propios
+ snapshot de `IdentityAPI`). Cada `identidad_<mod>.py` es un binding fino (≈10 líneas) → **cero
duplicación**, adaptadores 100 % homogéneos.

## 5. Eventos y telemetría

- **Eventos:** cada módulo publica `<modulo>.identidad.resuelta` **solo** en resoluciones
  significativas (nunca en el camino caliente `empresa_id`). Reutiliza el Event Bus existente.
- **Telemetría:** homogénea en todos los módulos; `telemetria()` combina contadores del adaptador con
  `IdentityAPI.telemetria()` (llamadas, errores, tiempos, cache hit/miss).

## 6. Justificación técnica

- **Factory compartido** en lugar de 12 copias → cumple "no duplicar código" + "adaptadores homogéneos".
- **Migración mecánica y determinista** (solo formas canónicas exactas de `_emp`/`_empresa`); las no
  canónicas se **omiten con seguridad** y se documentan → cero riesgo de reescritura incorrecta.
- **Fallback por módulo preservado** → comportamiento idéntico incluso si IOC fallara (cero regresiones).
- **Dirección de dependencias** respetada: `<módulo> → IdentityAPI → Service → Repository → Cache → IOC`.
- **Solo capa servicio**; no se toca capa datos (evita inversión `db → services`) ni la GUI ni la
  lógica funcional.

## 7. Compatibilidad

IOC v1/v2, IdentityAPI y los módulos ya migrados (CRM, Stock, Compras, Producción) **intactos**. Todos
los módulos nuevos preservan comportamiento y salida; multiempresa preservada; auditoría existente sin
duplicar. Aditivo y reversible (revertir = restaurar los `_emp`/`_empresa`; sin BD).

## 8. Resultado de pruebas (todas verdes)

| Prueba | Resultado |
|--------|-----------|
| `_emp`/`_empresa` idéntico al histórico (muestra de 28 módulos) | ✔ (`== fuentes.emp`) |
| Adaptadores homogéneos (empresa/tienda/almacén, contexto) | ✔ |
| IdentityContext | ✔ |
| Multiempresa (aislamiento) | ✔ |
| Eventos `<modulo>.identidad.resuelta` (p.ej. sat) en bus | ✔ |
| Telemetría homogénea (adaptador + IdentityAPI) | ✔ |
| Módulos funcionales intactos (contabilidad diario, etc.) | ✔ |
| AST de todos los ficheros modificados | ✔ |
| Compatibilidad IOC v1/v2 · CRM · Stock · Compras · Producción | ✔ |
| Smoke tests | ✔ **5 passed** |
| Regresiones | ✔ **cero** |

## 9. Informe técnico final

Con este bloque, **todos los módulos funcionales del ERP resuelven la identidad corporativa a través de
IOC / IdentityAPI**: TPV, Ventas/Facturación, Logística, RRHH, Finanzas, Calidad, SAT, GMAO,
Documentación, Fiscalidad, Contabilidad y Tesorería se suman a CRM, Stock, Compras y Producción. La
capa de servicios queda prácticamente libre de resolución propia de identidad (salvo los seams de
infraestructura documentados), y la base queda lista para **retirar progresivamente los mecanismos
heredados** (`fuentes.emp`/`empresa_actual_id` directos) cuando la migración complete su última fase
(capa de datos + infraestructura).

### Anexo — Ficheros
- Nuevo factory: `src/services/identidad/adaptador.py`
- 12 adaptadores nuevos: `services/{tpv,facturacion,logistica,rrhh,finanzas,calidad,sat,gmao,documental,fiscal,contabilidad,tesoreria}/identidad_*.py`
- 67 seams migrados (`_emp`/`_empresa`) en los 13 paquetes funcionales.
- Sin migración de BD; sin cambios en IOC, IdentityAPI, lógica funcional ni GUI.
- Eventos: `<modulo>.identidad.resuelta` por módulo.
