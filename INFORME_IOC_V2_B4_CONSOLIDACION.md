# IOC v2.0 — BLOQUE IV: Consolidación final y plan de retirada del legado

> Fase de **análisis, diseño y documentación**. No se ha eliminado legado, no se ha tocado lógica
> funcional/GUI, no hay migraciones ni commits. Único artefacto nuevo: la **fachada de identidad para
> la capa de datos** (aditiva, no cableada). Verificado; smoke 5 passed; cero regresiones.

---

## PARTE A — Auditoría global de mecanismos heredados

Conteo real (ocurrencias en `src/**/*.py`):

| Mecanismo | Ocurrencias | Notas |
|-----------|-------------|-------|
| `empresa_actual_id` | 545 | resolución canónica de empresa (147 svc · 44 db · 33 gui + otros) |
| `EMPRESA_DEFAULT_ID` | 342 | *fallback* raíz multiempresa (constante, NO retirable) |
| `def _emp` | 245 | helpers de empresa (incluye los 86 ya enrutados a IOC) |
| `tienda_actual_id` | 83 | resolución de tienda de contexto |
| `fuentes.emp` | 57 | wrapper del Gemelo (legado a retirar) |
| `def _empresa` | 45 | variante del helper de empresa |
| `almacen_actual` | 36 | resolución de almacén de contexto |
| `tienda_actual_id_int` | 18 | variante entera de tienda |
| `ref_tienda` / `ref_almacen` | 18 / 16 | feature legada «Asignar referencia» (conservada, Strangler) |

**Clasificación de seams de servicio (`_emp`/`_empresa`):** 175 ficheros; **86 migrados a IOC**
(marca «Bloque III»); **89 pendientes**.

**Criticidad:** baja. Todos son resolución de empresa/tienda equivalentes; el riesgo de retirada es
bajo porque IOC ya envuelve la misma fuente de verdad (`db.empresa`).

## PARTE B — Auditoría de la capa de datos (`db/*`)

- **24 ficheros** `db/*` con helper `_emp`/`_empresa`; **19** con `tienda_actual_id`.
- **Todos** contienen **lógica de dominio** (SQL de negocio) **además** del seam de identidad.

Clasificación para migración del **seam** (no de la lógica):

| Categoría | Descripción | Ejemplos |
|-----------|-------------|----------|
| **Migrables** | El helper resuelve solo empresa; se puede sustituir por `db.identidad_contexto.empresa_id` | `db/proveedores.py`, `db/reabastecimiento.py`, `db/pagos_proveedor.py`, `db/stock_almacen.py` |
| **Parcialmente migrables** | Resuelven empresa **+ tienda** entrelazadas (tupla) | `db/kardex.py`, `db/lotes.py`, `db/mermas.py`, `db/pedidos.py` |
| **No migrables (del seam)** | Derivan empresa de un registro/dominio, no de contexto | `fiscal/evidencias._empresa_de(registro)` (en servicios; equivalente en db) |

**La lógica de dominio NO se migra en ningún caso** — solo el seam de identidad.

## PARTE C — Fachada de identidad para la capa DB (diseñada e implementada, no cableada)

Nuevo `src/db/identidad_contexto.py` (**aditivo, no invasivo, no cableado**):
- Expone `empresa_id()`, `tienda_id()`, `tienda_id_int()`, `almacen_id()`.
- Por defecto resuelve con las funciones canónicas de `db.empresa` (**comportamiento idéntico**).
- **Inversión de dependencias correcta:** la capa DB define el registro; la capa de servicios (IOC)
  puede **inyectar** un resolver más rico en el arranque vía `registrar_resolver(...)`. Así `db/*`
  llamará a esta fachada (db → db) sin que `db` importe `services` → **no invierte capas**.
- **Verificado:** por defecto devuelve lo canónico; con resolver inyectado delega; al retirar el
  resolver, vuelve a lo canónico. No cambia nada hasta que se migren los seams de `db/*` a ella.

## PARTE D — Plan de retirada del código heredado

**Orden de retirada (por fases, sin romper compatibilidad):**

1. **Fase L1 — Servicios funcionales pendientes (bajo riesgo):** migrar los seams restantes de
   `contratos`, `logistics` y las 3 variantes de CRM (`campanias/objetivos/rutas`) al adaptador de su
   módulo (mismo patrón Strangler). *Dependencia:* adaptadores ya existentes. *Riesgo:* bajo.
2. **Fase L2 — Infra/Enterprise (opcional):** homogeneizar los seams de `bi_corp/distribucion/
   resiliencia/actividad/gobierno/autonomia/saas/…` con un adaptador `identidad_infra` (o dejarlos,
   ya que no son módulos de negocio). *Riesgo:* bajo; *valor:* medio.
3. **Fase L3 — Capa de datos:** migrar los helpers `_emp`/`_empresa` de `db/*` a
   `db.identidad_contexto.empresa_id` (db → db). Cablear opcionalmente el resolver IOC en el arranque.
   *Dependencia:* fachada C (lista). *Riesgo:* medio (capa crítica) → migrar fichero a fichero con
   pruebas.
4. **Fase L4 — Retirada de `fuentes.emp`:** una vez todos los seams pasan por IOC/fachada, sustituir
   las llamadas directas a `fuentes.emp` por `empresa_id` y **deprecar** `gemelo.fuentes.emp`
   (mantener un *shim* un ciclo). *Riesgo:* bajo (equivalencia probada).
5. **Fase L5 — GUI:** migrar los 33 ficheros de `gui/*` que llaman `empresa_actual_id` para que usen
   `IdentityAPI`/adaptador (no acceso directo). *Riesgo:* bajo; *valor:* alto (regla «GUI nunca SQL»).
6. **Fase L6 — Constantes:** `EMPRESA_DEFAULT_ID` **se mantiene** (semilla multiempresa); no se retira.

**Estrategia de rollback (todas las fases):** cada seam conserva su *fallback* original; revertir =
restaurar el cuerpo del helper. Sin cambios de BD → rollback inmediato por control de versiones.

**Compatibilidad:** en todas las fases el comportamiento observable permanece idéntico (equivalencia
`empresa_id == fuentes.emp == id_empresa or empresa_actual_id`, ya verificada en Bloques III).

## PARTE E — Detección de duplicidades

- **Resolución de empresa duplicada** en ~175 helpers `_emp`/`_empresa` (2-4 formas). **Consolidación
  propuesta (no aplicada):** todos delegan en `empresa_id` (servicios: adaptador de módulo; datos:
  `db.identidad_contexto`). Ya hecho en 86; pendiente en el resto.
- **`gemelo.fuentes.emp` ⇆ `identidad._base.emp`:** equivalentes. **Propuesta:** `_base.emp` es la
  canónica; `fuentes.emp` queda como *shim* deprecado (Fase L4).
- **Adaptadores:** los 12 nuevos comparten el **factory único** (`identidad/adaptador.py`) → sin
  duplicación. Los 4 pre-factory (crm/stock/compras/produccion) son standalone con interfaz adaptada a
  su dominio (todos comparten `empresa_id/contexto/telemetria`). **Propuesta (opcional):** refactor a
  factory para uniformidad total (bajo valor, se pospone).
- **Código muerto:** no detectado en IOC; los adaptadores standalone no son código muerto (en uso).

## PARTE F — Hardening del motor IOC

| Área | Estado | Oportunidad (no aplicada) |
|------|--------|---------------------------|
| **Caché** | TTL 300s, clave `(empresa,ns,key)`, suscrita a `*` del bus | métricas de tamaño/evicción; TTL por tipo de entidad |
| **Invalidación** | por Event Bus (`identidad.*`) + explícita en mutaciones | invalidación selectiva por entidad (hoy por empresa) |
| **Event Bus** | reutilizado; eventos de UI/dominio separados | *batching* de eventos en operaciones masivas |
| **Telemetría** | contadores + tiempos + cache hit/miss; lista Prometheus/OTel | exportador Prometheus real (Fase futura) |
| **Versionado** | `API_VERSION=v2`, `VERSIONES_SOPORTADAS=(v1,v2)` | activar `v3` cuando proceda |
| **Memoria** | caché en proceso, dict con TTL | límite de tamaño/LRU si crece el nº de entidades |
| **Cuellos de botella** | `empresa_id` en camino caliente sin eventos (correcto) | ninguno crítico detectado |

**Sin cambios de comportamiento**: solo se documentan oportunidades.

## PARTE H — Validaciones (todas verdes)

| Validación | Resultado |
|-----------|-----------|
| IOC v1 / v2 | ✔ |
| IdentityAPI (`v2`, resolver) | ✔ |
| Adaptadores (16; interfaz común `empresa_id/contexto/telemetria`) | ✔ (12 factory uniformes + 4 dominio) |
| Módulos migrados (muestra 28) | ✔ (`== fuentes.emp`) |
| Fachada DB (canónica + resolver inyectado + restaurada) | ✔ |
| Multiempresa / Multitienda | ✔ |
| Auditoría / RBAC (7 permisos) / Scheduler (jobs IOC) | ✔ |
| Event Bus / Caché (suscrita) / Telemetría | ✔ |
| Compatibilidad SaaS (id_empresa + grupo) | ✔ |
| Smoke tests | ✔ **5 passed** |
| Regresiones | ✔ **cero** |

## PARTE I — Informe final de consolidación

- **Estado real IOC:** núcleo (v1) + gobierno/jerarquía (v2 B1) + motor Repository/Service/Resolver/
  Validation/Cache (B1.6-1.10) + IdentityAPI (B2.1) + adopción de **todos los módulos funcionales**
  (B3) + **fachada de datos preparada** (B4). Operativo y verificado.
- **Adopción completada:**
  - **Módulos funcionales de negocio: 100 %** (CRM, Stock, Compras, Producción, TPV, Ventas/
    Facturación, Logística, RRHH, Finanzas, Calidad, SAT, GMAO, Documentación, Fiscalidad,
    Contabilidad, Tesorería).
  - **Seams de servicio totales: 86/175 ≈ 49 %** (el resto son infra/Enterprise + 3 variantes CRM).
  - **Capa de datos: 0 %** migrada (fachada lista; Fase L3).
  - **GUI: 0 %** migrada (Fase L5).
- **Código heredado restante:** 89 seams de servicio (infra/Enterprise), 24 helpers en `db/*`, 33
  ficheros GUI con `empresa_actual_id`, 57 usos de `fuentes.emp`.
- **Riesgos pendientes:** (1) capa de datos es crítica → migrar con pruebas por fichero; (2) GUI con
  acceso directo → migrar a IdentityAPI; (3) `fuentes.emp` debe deprecarse tras L1-L3.
- **Acciones futuras recomendadas:** ejecutar Fases L1→L6 en orden; exportador Prometheus real;
  refactor opcional de los 4 adaptadores standalone al factory.
- **Componentes preparados para eliminar (cuando termine la migración):** helpers `_emp`/`_empresa`
  duplicados (una vez todos delegan), `gemelo.fuentes.emp` (tras *shim*).
- **Componentes que deben mantenerse:** `EMPRESA_DEFAULT_ID` (semilla), `db.empresa.*` (canónico y
  base de IOC), la feature `ref_tienda/ref_almacen` (compatibilidad).
- **Estado del patrón Strangler:** avanzado — la nueva infraestructura (IOC/IdentityAPI/adaptadores/
  fachada db) coexiste con el legado; el legado se retira por fases sin romper nada.
- **Preparación para IOC v3:** arquitectura lista (`VERSIONES_SOPORTADAS` incluye la ranura; fachada
  de datos y factory homogéneo permiten evolucionar sin rediseño). v3 podría aportar: resolución
  federada SaaS multi-nodo, caché distribuida, exportador de telemetría y permisos visuales heredados.

**Conclusión:** IOC queda **consolidado** como fuente única de identidad de los módulos funcionales,
con un **mapa preciso del legado restante** y un **plan de retirada por fases con rollback**, listo
para la limpieza final y la evolución a IOC v3 sin riesgo para el ERP.
