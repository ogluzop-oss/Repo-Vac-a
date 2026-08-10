# IOC v2.0 — BLOQUE 2.1: API Interna Corporativa de Identidad (Identity API)

> Capa de fachada pública sobre el motor IOC v2. 100 % lógica (sin migración). Aditiva, Strangler,
> multiempresa, auditada. Verificada; smoke 5 passed; cero regresiones.

## 1. Auditoría previa

Verificado que el motor IOC v2 (Bloque 1.6–1.10) está intacto y operativo:
`IdentityService`, `IdentityResolver`, `IdentityValidationEngine`, `IdentityRepository`,
`IdentityCache` (singletons). Falta una **puerta pública única** por encima de ellos para que los
módulos no toquen Repository/Cache/SQL. Eso es lo que añade este bloque.

## 2. Arquitectura

```
ERP (consumidores)
   └─> IdentityAPI  (identidad/api.py)   ← ÚNICO punto de entrada permitido
          └─> IdentityService / IdentityResolver / IdentityValidationEngine
                 └─> IdentityRepository (solo lectura) → IdentityCache → BD IOC
```

`IdentityRepository` deja de ser visible para los consumidores: usan **solo** `api()`. La API nunca
ejecuta SQL ni devuelve objetos internos del Repository.

## 3. Contratos públicos (métodos)

Todos resuelven `id_empresa` automáticamente (sin consultas cruzadas), miden telemetría y publican
eventos. Devuelven **modelos públicos**.

| Método | Retorno | Errores/Excepciones |
|--------|---------|---------------------|
| `resolver(**ctx)` / `resolver_por_documento` | `IdentityResult` | `IdentityException` (inesperado) |
| `resolver_por_uuid(uuid)` | `IdentityResult` | **`IdentityNotFound`** si no existe |
| `resolver_por_codigo(tipo,valor)` | `IdentityResult` | `IdentityNotFound` |
| `resolver_por_terminal/usuario/tienda/almacen/empresa` | `IdentityResult` | — |
| `obtener_contexto(**ctx)` | `dict` (IdentityContext) | `IdentityNotFound` si no resoluble |
| `obtener_jerarquia(id_centro)` | `IdentityHierarchy` | `IdentityHierarchyError` |
| `obtener_padres/obtener_hijos(id_centro)` | `list[ref]` | — |
| `validar(id_centro, estricto=False)` | `dict` (validation) | `IdentityValidationError` si `estricto` |
| `existe(uuid)` | `bool` | — |
| `buscar / buscar_por_tipo / _estado / _empresa / _grupo` | `IdentitySearchResult` | — |
| `telemetria()` | `dict` | — |

Tipado fuerte; nunca se devuelven diccionarios genéricos cuando existe un modelo.

## 4. Modelos públicos (`identidad/modelos.py`)

`IdentityResult` (resolución: ok/uuid/resumen/contexto/error), `IdentitySearchResult` (búsquedas:
total/resultados), `IdentityHierarchy` (ascendentes/descendientes), `IdentitySummary` (cabecera),
`IdentityReference` (referencia mínima estable), `IdentityError` (error serializable). Todos
dataclasses con `to_dict()`. **Nunca** se exponen objetos internos del Repository.

## 5. Excepciones (`identidad/excepciones.py`)

Base `IdentityException` (con `codigo` + `to_error()→IdentityError`) y:
`IdentityNotFound`, `IdentityConflict`, `IdentityValidationError`, `IdentityPermissionError`,
`IdentityHierarchyError`, `IdentityStateError`. **No se lanzan excepciones genéricas**: las
inesperadas se envuelven en `IdentityException`.

## 6. Flujo de llamadas

Cada método pasa por `_medir(metodo, fn)`: publica `identity.api.called`, ejecuta la función
(delegando en Service/Resolver/Validation), y en `finally` registra telemetría (tiempo, llamadas,
errores). Si falla, publica `identity.api.failed` (y `identity.api.validation_failed` en validaciones)
y propaga la excepción tipada. La API construye el modelo público a partir del `IdentityContext`.

## 7. Telemetría

`_Telemetria` en proceso: nº de llamadas, errores, validaciones fallidas, tiempo total/medio y
desglose por método; además expone `cache_hits/miss/ratio` leídos del `IdentityCache`. **Preparada
para Prometheus/OpenTelemetry** (snapshot estructurado) sin integrar herramientas externas aún.

## 8. Versionado

`API_VERSION="v2"`, `VERSIONES_SOPORTADAS=("v1","v2")`; `api(version=...)` es el punto de acceso
(fábrica) preparado para **v1/v2/v3** sin romper compatibilidad. Solo v2 implementado (por diseño).

## 9. Compatibilidad

IOC v1/v2, Repository/Service/Resolver/Validation/Cache **intactos** y reutilizados. Sin migración,
reversible por construcción. Multiempresa (auto-resolución de `id_empresa`, sin cruces). Módulos
funcionales, documentos, TPV, SOMA y navegación **no tocados**. Patrón Strangler: los módulos migran
progresivamente a `api()`.

## 10. Pruebas realizadas (todas verdes)

| Prueba | Resultado |
|--------|-----------|
| Resolución por UUID / código / terminal / documento / usuario | ✔ (IdentityResult) |
| `resolver_por_codigo` → uuid correcto | ✔ |
| Jerarquía en contexto (`SUBCENTRO→CENTRO→EMPRESA→GRUPO`) | ✔ |
| `existe` (true/false) | ✔ |
| `obtener_contexto` / `obtener_jerarquia` / `obtener_hijos` | ✔ |
| Búsquedas (`buscar_por_tipo/_estado`) → IdentitySearchResult | ✔ |
| Validación (`validar` dict) | ✔ |
| **Excepción tipada** `IdentityNotFound` en UUID inexistente | ✔ (corregido: la existencia se decide por el Repository, no por la empresa del contexto) |
| Eventos `identity.api.*` | ✔ |
| Telemetría (llamadas/errores/tiempo/cache/por_método) | ✔ (11 métodos) |
| Multiempresa (auto-resolución, sin cruces) | ✔ |
| Compatibilidad IOC v1 / v2 | ✔ |
| Smoke tests | ✔ **5 passed** |
| Regresiones | ✔ **cero** |

## 11. Informe final

La **Identity API** queda como única interfaz pública oficial de identidad del ERP: fachada tipada
sobre el motor IOC v2, con modelos públicos, excepciones propias, telemetría, eventos y versionado
preparado. Ningún consumidor necesita ya (ni debe) acceder a Repository/Cache/SQL. La base está lista
para la adopción progresiva por los +20 módulos mediante Strangler.

### Anexo — Ficheros
- `src/services/identidad/api.py` (IdentityAPI + telemetría + versionado)
- `src/services/identidad/modelos.py` (6 modelos públicos)
- `src/services/identidad/excepciones.py` (6 excepciones + base)
- Sin migración. Eventos: `identity.api.{called,failed,validation_failed}`.
