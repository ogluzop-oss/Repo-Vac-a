# IOC v2.0 — BLOQUE 1.6–1.10: Motor Corporativo de Identidad
## Repository · Service · Resolver · Validation Engine · Cache

---

# PARTE A — Informes previos (antes de implementar)

## A.1 Auditoría técnica

IOC v2 (Bloques 1 y 1.x) ya provee, **verificado**:
- Tablas: `centros_trabajo` (extendida: tipo/nivel/estado_gobierno/propiedad/jerarquía padre),
  `ioc_centro_codigos`, `ioc_terminales`, `ioc_impresoras`, `ioc_grupos_empresariales`,
  `ioc_identidad_auditoria`; `empresas`/`tiendas`/`almacen` reutilizadas.
- Servicios de dominio: `identidad/{centros,codigos,terminales,impresoras,grupos,jerarquia,gobierno,
  identidad(fachada),tipos,_base}.py`.
- Infra: Event Bus (`eventos.publicar` + `suscribir("*",handler)`), Scheduler/JobRegistry, RBAC
  (`identidad.*`), auditoría (`log_auditoria`), multiempresa (`id_empresa`).
- Inversión de dependencias correcta (IOC solo depende de db/infra).

**Carencia que cubre este bloque:** no existe todavía una **capa de motor** (Repository/Service/
Resolver/Validation/Cache) que unifique el acceso y la resolución de identidad. Hoy cada consumidor
tendría que llamar a varios servicios sueltos. Este bloque crea la API interna única.

## A.2 Componentes existentes reutilizables

| Componente | Reutilización en este bloque |
|-----------|------------------------------|
| `identidad/centros.py` | Repository.get_centro / listar / hijos |
| `identidad/grupos.py` | Repository.get_grupo / empresas_de_grupo |
| `identidad/terminales.py`, `impresoras.py` | Repository.get_terminal / get_impresora |
| `identidad/codigos.py` | Repository.buscar_por_codigo / códigos del centro |
| `identidad/jerarquia.py` | Repository.get_ascendentes/descendientes + config heredada |
| `identidad/gobierno.py` | Service.archivar/activar/mover (estados/soft-delete/auditoría) |
| `identidad/identidad.py::identidad_documento` | base para Resolver.resolver_por_documento |
| `eventos.publicar` + `suscribir("*")` | Cache: invalidación por Event Bus (patrón Gemelo) |
| `db.empresa`, `db.tiendas` | Repository.get_empresa / resolución por tienda/almacén |
| `log_auditoria` | Service: auditoría con duración |

**No se crean tablas nuevas**: el bloque es 100 % capa de servicios (lógica).

## A.3 Dependencias

- Dirección obligatoria: `ERP → Service → Repository → Cache → BD`;
  `Resolver → Repository`; `ValidationEngine → Resolver → Repository`.
- Solo `db.*` + `services.eventos`/`scheduler` + `services.identidad.*`. Cero módulos funcionales.
- Nueva dependencia interna: los servicios de dominio v2 pasan a ser consumidos **a través del
  Repository** (los consumidores externos usarán solo el Service). Los servicios de dominio siguen
  existiendo (compatibilidad), pero la puerta pública recomendada será el Service.

## A.4 Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|-----------|
| Caché compartiendo datos entre empresas | Clave de caché incluye `id_empresa`; aislamiento estricto |
| Caché obsoleta | TTL configurable + invalidación por Event Bus (suscripción `*`) + invalidación explícita en mutaciones |
| Duplicar lógica de dominio | Repository/Service **componen** los servicios v2; no reimplementan SQL |
| Romper IOC v2 | Todo aditivo; los servicios v2 quedan intactos y siguen funcionando |
| GUI→SQL directo | La regla queda documentada; la API única es el Service (los módulos migran por Strangler) |
| Bus sin consumidores previos | La suscripción es idempotente y best-effort (no rompe si el bus está vacío) |

## A.5 Cambios previstos (todos aditivos, sin migración)

Nuevos módulos en `src/services/identidad/`:
- `cache.py` — `IdentityCache` (TTL, multiempresa, invalidación por Event Bus).
- `repository.py` — `IdentityRepository` (punto único de acceso, sobre la caché).
- `resolver.py` — `IdentityResolver` + `IdentityContext` (resolución a contexto completo).
- `validation.py` — `IdentityValidationEngine` + `IdentityValidationResult` (validación estructurada).
- `service.py` — `IdentityService` (fachada única para consumidores) + auditoría con duración.
- Exposición de *singletons* y funciones de conveniencia en `identidad/__init__` (opcional, no rompe).

Eventos nuevos (sobre el bus existente): `identidad.resuelta`, `identidad.validada`,
`identidad.actualizada`, `identidad.movida`, `identidad.sincronizada`, `identidad.cache.actualizado`,
`identidad.cache.invalidado`.

---

# PARTE B — Informe final (tras la implementación)

## B.1 Arquitectura final

Capa de motor de identidad añadida sobre IOC v2, respetando la dirección de dependencias obligatoria:

```
ERP (consumidores)
   └─> IdentityService ──> IdentityRepository ──> IdentityCache ──> BD (tablas IOC)
IdentityResolver ─────────> IdentityRepository ──> IdentityCache
IdentityValidationEngine ─> IdentityResolver ────> IdentityRepository
```

- La **única puerta pública** para los módulos es `service()` (`IdentityService`).
- Repository es solo lectura; las mutaciones se gobiernan en el Service (que reutiliza
  `gobierno`/`centros`).
- La caché es transversal a Repository/Resolver/Service; los módulos nunca la tocan.
- Prohibido `GUI → SQL`: todo pasa por IOC.

## B.2 Clases creadas

| Clase | Fichero | Rol |
|-------|---------|-----|
| `IdentityCache` | `identidad/cache.py` | Caché TTL, multiempresa, invalidación por Event Bus |
| `IdentityRepository` | `identidad/repository.py` | Punto único de acceso (getters + búsquedas) |
| `IdentityResolver` + `IdentityContext` | `identidad/resolver.py` | Resolución a contexto completo |
| `IdentityValidationEngine` + `IdentityValidationResult` | `identidad/validation.py` | Validación estructurada |
| `IdentityService` | `identidad/service.py` | Fachada única + ciclo de vida + auditoría con duración |

Singletons de proceso expuestos por `cache()`, `repository()`, `resolver()`, `validation_engine()`,
`service()`.

## B.3 Flujo Repository → Service → Resolver

- **Service.crear/actualizar/mover/archivar/activar/desactivar** → gobierno/centros (mutación) +
  `cache.invalidar(empresa)` + auditoría (duración) + evento.
- **Service.resolver_identidad** → `IdentityResolver` → `IdentityRepository` (con caché) →
  `IdentityContext` (empresa/grupo/centro/terminal/tienda/jerarquía/propietario/responsable/códigos/
  estado). Publica `identidad.resuelta`.
- **Repository** sirve cada getter vía `cache.obtener_o_calcular(empresa, namespace, key, calc)`.

## B.4 Flujo del Validation Engine

`IdentityValidationEngine` → `IdentityResolver`/`IdentityRepository`. Valida UUID/existencia, empresa,
tipo, nivel, estado oficial, jerarquía (padre existente, ciclos, cruce de empresa), códigos
(duplicados), terminales, transiciones y consistencia de contexto. Devuelve `IdentityValidationResult`
(**bloqueantes / errores / avisos / informativos** + `valido`). Reutilizable por Workflow/Scheduler/
SOMA/Documentos/API/Importadores. Publica `identidad.validada`.

## B.5 Flujo de la Cache

Clave `(id_empresa, namespace, key)` → **aislamiento multiempresa estricto**. TTL configurable por
entrada. Suscrita a `'*'` en el Event Bus (patrón del Gemelo): cualquier `identidad.*` de mutación
invalida la caché de esa empresa (evitando bucles con los eventos de resolución/validación/cache).
Además, el Service invalida explícitamente en cada mutación. Publica `identidad.cache.invalidado`.

## B.6 Integración con IOC

- Reutiliza los servicios de dominio v2 (`centros/grupos/terminales/impresoras/codigos/jerarquia/
  gobierno`) por composición; **cero** reimplementación de SQL.
- Reutiliza Event Bus, `log_auditoria` y multiempresa existentes. Sin migración nueva.
- Inversión de dependencias intacta: la capa de motor solo depende de `db.*`, `services.eventos/
  scheduler` y `services.identidad.*`.

## B.7 Compatibilidad garantizada

- IOC v1 e IOC v2 B1 **intactos**; los servicios de dominio siguen funcionando igual.
- `configuraciones.ref_tienda/ref_almacen` conservados (Strangler).
- Idempotente, reversible (no hay cambios de esquema), auditado, multiempresa, multitienda, SaaS-ready.
- Sin cambios en módulos funcionales, documentos, TPV, SOMA ni navegación.

## B.8 Pruebas realizadas (todas verdes)

| Prueba | Resultado |
|--------|-----------|
| Repository (getters + búsquedas) | ✔ |
| Service (crear/actualizar/mover/archivar/activar/desactivar/clonar/sincronizar) | ✔ |
| Resolver → IdentityContext completo | ✔ (jerarquía `SUBCENTRO→CENTRO→EMPRESA→GRUPO`) |
| Validation Engine (estructurado) | ✔ (bloqueantes/errores/avisos/informativos) |
| Transición inválida detectada | ✔ (bloqueante) |
| Mover con guard de ciclo | ✔ (rechazado) |
| Cache (hits + suscripción bus) | ✔ (hits>0, suscrito_bus=True) |
| Invalidación por Event Bus | ✔ (entrada desaparece tras evento) |
| Multiempresa (aislamiento) | ✔ |
| Jerarquías / Terminales / Impresoras / UUID / Códigos | ✔ |
| Event Bus / Auditoría (con duración) / Scheduler | ✔ |
| Compatibilidad IOC v2 | ✔ |
| Smoke tests | ✔ **5 passed** |
| Regresiones | ✔ **cero** |

## B.9 Informe técnico final

IOC deja de ser solo infraestructura de datos y pasa a ser un **motor corporativo de identidad**: una
API interna única (`IdentityService`) que centraliza acceso (`Repository`), resolución (`Resolver` →
`IdentityContext`), validación (`ValidationEngine` → resultado estructurado) y rendimiento (`Cache`
multiempresa con invalidación por Event Bus). Toda la lógica se **compone** sobre IOC v2 sin duplicar
ni romper nada; la arquitectura queda lista para que CRM/RRHH/TPV/Producción/Stock/Compras/Calidad/
SAT/Finanzas/BI/SOMA la adopten progresivamente (Strangler) como **única fuente de verdad de
identidad**.

### Anexo — Ficheros del Bloque 1.6–1.10
- `src/services/identidad/{cache,repository,resolver,validation,service}.py` (5 clases nuevas)
- Sin migración (capa lógica). Sin cambios en módulos funcionales.
- Eventos: `identidad.{resuelta,validada,actualizada,movida,sincronizada,cache.actualizado,cache.invalidado}`.
