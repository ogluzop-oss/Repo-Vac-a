# Motor Corporativo de Identidad (IOC) — Documentación técnica oficial

> Documentación de referencia para desarrolladores de Smart Manager AI. IOC es el **Identity Core**:
> la única fuente de verdad para identificar cualquier entidad operativa del ERP.

## 1. Qué es IOC

IOC (Identidad Operativa de Centros) resuelve, valida y cachea la identidad corporativa: empresa,
grupo empresarial, centro (con jerarquía), tienda, almacén, terminal, impresora y usuario. La
identidad es un **UUID permanente**; todo lo visible (nombre, código, referencia) es **atributo**.

## 2. Arquitectura y capas

```
ERP (módulos funcionales)
  └─> Adaptador de módulo (services/<mod>/identidad_<mod>.py)
        └─> IdentityAPI (services/identidad/api.py)      ← única puerta pública
              └─> IdentityService (service.py)           ← mutaciones + ciclo de vida
                    └─> IdentityRepository (repository.py) ← acceso único (solo lectura)
                          └─> IdentityCache (cache.py)     ← TTL + invalidación por Event Bus
                                └─> BD IOC (tablas)
  IdentityResolver (resolver.py) ─────> Repository
  IdentityValidationEngine (validation.py) ─> Resolver → Repository
  Capa de datos (db/*) ──> db/identidad_contexto.py (fachada; resolver IOC inyectable)
```

**Dirección de dependencias (estricta):** `ERP → IdentityAPI → Service → Repository → Cache → BD`.
IOC **nunca** importa módulos funcionales. La capa `db/*` usa la fachada `db/identidad_contexto.py`
(inversión de dependencias por inyección; `db` no importa `services`).

## 3. Modelo de datos (migraciones 0121, 0122)

- `centros_trabajo` (extendida): `id_centro` (UUID), `tipo`, `nivel` (GRUPO/CENTRO/SUBCENTRO/ZONA),
  `id_centro_padre`, `estado_gobierno`, `id_propietario`, `id_responsable_operativo`, alias, etc.
- `ioc_grupos_empresariales` (UUID) + `empresas.id_grupo` — nivel superior (holding/grupo/franquicia).
- `ioc_centro_codigos` — códigos operativos múltiples e independientes (VISIBLE/FISCAL/TPV/…).
- `ioc_terminales`, `ioc_impresoras` — dispositivos con UUID.
- `ioc_identidad_auditoria` — auditoría enriquecida (valor anterior/nuevo, IP, terminal).
- Compatibilidad: `configuraciones.ref_tienda/ref_almacen` (feature legada, conservada).

## 4. Ciclo de vida / gobierno

- Estados oficiales: `ACTIVO → SUSPENDIDO → ARCHIVADO → ELIMINACION_PENDIENTE → HISTORICO`
  (transiciones validadas). **Nunca borrado físico** (soft delete por transición).
- Campos inmutables: `id`/UUID, `id_empresa`, `fecha_creacion` (guard que rechaza y audita).
- Propiedad: propietario/creador/modificador/responsable operativo (auditados).
- API de gobierno: `identidad/gobierno.py` (`modificar_atributo`, `transicionar_estado`, `soft_delete`,
  `set_propiedad`, `historial_identidad`).

## 5. Flujo de resolución

1. El módulo llama a su adaptador (`identidad_<mod>.contexto(...)` o `identidad(...)`).
2. El adaptador llama a `IdentityAPI` → `IdentityResolver` → `IdentityRepository` (con caché).
3. Se devuelve un `IdentityContext` (empresa/grupo/centro/tienda/almacén/terminal/jerarquía/
   propietario/responsable/códigos/estado). La API lo envuelve en `IdentityResult` (modelo público).

## 6. IdentityAPI (puerta pública)

`services/identidad/api.py` — `api()` (singleton). Métodos: `resolver`, `resolver_por_uuid/codigo/
terminal/documento/usuario/tienda/almacen/empresa`, `obtener_contexto/jerarquia/padres/hijos`,
`validar`, `existe`, `buscar/buscar_por_tipo/estado/empresa/grupo`, `telemetria`.
- **Modelos públicos** (`modelos.py`): `IdentityResult`, `IdentitySearchResult`, `IdentityHierarchy`,
  `IdentitySummary`, `IdentityReference`, `IdentityError`. Nunca se exponen objetos internos.
- **Excepciones** (`excepciones.py`): `IdentityNotFound/Conflict/ValidationError/PermissionError/
  HierarchyError/StateError` (base `IdentityException`).
- **Versionado:** `API_VERSION="v2"`, `VERSIONES_SOPORTADAS=("v1","v2")` (ranura para v3).

## 7. Validación

`IdentityValidationEngine` (`validation.py`) → `IdentityValidationResult` con
`bloqueantes/errores/avisos/informativos`. Valida UUID, jerarquía (ciclos, cruce de empresa), estado,
transiciones, códigos duplicados, terminales, consistencia. Reutilizable por Workflow/Scheduler/SOMA/
Documentos/API/Importadores.

## 8. Caché

`IdentityCache` (`cache.py`, singleton `cache()`): TTL configurable (300s por defecto), clave
`(id_empresa, namespace, key)` con **aislamiento multiempresa estricto**. Invalidación automática por
Event Bus (suscrita a `*`; cualquier `identidad.*` de mutación invalida la empresa afectada) +
invalidación explícita en mutaciones del Service. Métricas: hits/miss/ratio.

## 9. Eventos (Event Bus)

Se reutiliza el bus existente (`services.eventos.publicar` / `bus.suscribir`). Tipos:
- Núcleo: `identidad.centro_creado/modificado/archivado`, `identidad.codigo_asignado`,
  `identidad.terminal_registrado/asignado`, `identidad.cambio_auditado`,
  `identidad.cache.invalidado`.
- API: `identity.api.called/failed/validation_failed`.
- Por módulo (adaptadores): `<modulo>.identidad.resuelta` (solo resoluciones significativas).

## 10. Telemetría

Cada adaptador y la IdentityAPI exponen `telemetria()`: nº de llamadas, errores, tiempos (total/
medio), desglose por método y cache hits/miss. Preparada para Prometheus/OpenTelemetry (sin integrar
herramientas externas aún).

## 11. Adaptadores por módulo (Strangler)

- **Factory homogéneo:** `services/identidad/adaptador.py::construir("<modulo>")` → interfaz común
  `empresa_id, tienda_actual, almacen_actual, empresa_tienda_almacen, contexto, identidad, telemetria`.
- **Adaptadores:** `services/<mod>/identidad_<mod>.py` (16): crm, stock, compras, produccion (standalone)
  + tpv, facturacion, logistica, rrhh, finanzas, calidad, sat, gmao, documental, fiscal, contabilidad,
  tesoreria (factory).
- **Regla de uso:** los módulos resuelven identidad **solo** por su adaptador (o IdentityAPI); nunca
  por SQL/Repository/Cache directo. `empresa_id` es camino caliente (sin eventos, con *fallback*);
  `identidad(...)` publica evento significativo.

## 12. Estrategia Strangler y plan de retirada del legado

- La nueva infraestructura coexiste con el legado (`fuentes.emp`, `empresa_actual_id`); el legado se
  retira por fases (ver `INFORME_IOC_V2_B4_CONSOLIDACION.md`, Parte D): L1 servicios pendientes → L2
  infra → L3 capa de datos (vía `db/identidad_contexto.py`) → L4 deprecar `fuentes.emp` → L5 GUI →
  L6 conservar `EMPRESA_DEFAULT_ID`.
- **Rollback:** cada seam conserva su *fallback* original; sin cambios de BD.

## 13. RBAC y Scheduler

- Permisos (`seguridad/catalogo.py`): `identidad.ver/crear/modificar/eliminar/configurar/
  asignar_terminal/asignar_impresora`.
- Jobs opt-in (`scheduler_registry`): `identidad_validacion_centros`,
  `identidad_verificacion_terminales`, `identidad_sincronizacion`.

## 14. Multiempresa / Multitienda / SaaS

Todo se resuelve por `id_empresa` (UUID) y, para el nivel superior, `id_grupo` (holding/grupo/
franquicia). La caché aísla por empresa; los adaptadores nunca cruzan empresas. Base preparada para
SaaS multi-nodo (Fase v3).

## 15. Reglas para nuevos desarrollos

1. Para resolver identidad: usar el adaptador del módulo (`identidad_<mod>`) o `IdentityAPI`. **Nunca**
   `empresa_actual_id`/`fuentes.emp`/SQL directo en módulos nuevos.
2. Nueva pantalla/módulo: consumir `IdentityContext`; no crear ids de identidad propios.
3. Publicar `<modulo>.identidad.resuelta` solo en resoluciones significativas (no en camino caliente).
4. La identidad es UUID; los códigos son atributos (usar `ioc_centro_codigos`).
5. Respetar la dirección de dependencias; la capa de datos usa `db/identidad_contexto.py`.
