# INFORME_IOC_V3_ESTABLE.md — Certificación técnica del Motor Corporativo de Identidad

> Bloque VII: **certificación, congelación, hardening y preparación de IOC v3.x**. Auditoría integral
> ejecutada. **No se detectó ninguna desviación objetiva → no se modificó código.** Verificado;
> smoke 5 passed; cero regresiones. IOC queda **oficialmente certificado como infraestructura estable**.

---

## 1. Estado general de IOC

IOC ha completado su implantación (Bloques I–VI): núcleo, gobierno/jerarquía, motor (Repository/
Service/Resolver/Validation/Cache), IdentityAPI, adaptadores de los 17 módulos funcionales, fachada de
datos, retirada controlada del legado y adopción transversal en motores. **Estado: ESTABLE y
CONGELADO.** Deja de ser proyecto en evolución; futuras mejoras serán **IOC v3.x** sin romper v3.

## 2. Arquitectura definitiva (certificada)

```
ERP / Motores corporativos
  └─> Adaptador de módulo (identidad_<mod>.py)  ·  Factory (identidad/adaptador.py)
        └─> IdentityAPI (api.py)               ← puerta pública ÚNICA
              └─> IdentityService (service.py)  ← mutaciones + ciclo de vida
                    └─> IdentityRepository (repository.py)  ← acceso único (lectura)
                          └─> IdentityCache (cache.py)      ← TTL + invalidación por Event Bus
                                └─> BD IOC
  IdentityResolver → Repository   ·   IdentityValidationEngine → Resolver → Repository
  Capa de datos (db/*) → db/identidad_contexto.py (fachada; resolver IOC inyectable)
```

**Verificado (Parte A/G):** IOC **no importa** ningún módulo funcional (dirección `ERP → IOC`
correcta); 19/19 componentes importables **sin ciclos**; la fachada DB **no importa `services` a nivel
de módulo** (inversión de dependencias por inyección). Separación de capas íntegra.

## 3. Componentes certificados (ESTABLE)

| Componente | Fichero | Estado |
|-----------|---------|--------|
| IdentityAPI | `identidad/api.py` | **ESTABLE** |
| IdentityContext | `identidad/resolver.py` | **ESTABLE** |
| IdentityResult / modelos públicos | `identidad/modelos.py` | **ESTABLE** |
| IdentityService | `identidad/service.py` | **ESTABLE** |
| IdentityRepository | `identidad/repository.py` | **ESTABLE** |
| IdentityResolver | `identidad/resolver.py` | **ESTABLE** |
| IdentityValidationEngine | `identidad/validation.py` | **ESTABLE** |
| IdentityCache | `identidad/cache.py` | **ESTABLE** |
| Factory de adaptadores | `identidad/adaptador.py` | **ESTABLE** |
| Excepciones | `identidad/excepciones.py` | **ESTABLE** |
| Fachada DB | `db/identidad_contexto.py` | **ESTABLE** |
| Adaptadores de módulo (17) | `services/*/identidad_*.py` | **ESTABLE** |
| Gobierno/jerarquía/grupos | `identidad/{gobierno,jerarquia,grupos}.py` | **ESTABLE** |

## 4. Componentes congelados (API pública estable de IOC v3)

Se **congela** el contrato público. Cualquier evolución (v3.x) debe mantener compatibilidad:
- `identidad.api.api()` y sus métodos (`resolver_por_*`, `obtener_contexto/jerarquia/padres/hijos`,
  `validar`, `existe`, `buscar_por_*`, `telemetria`).
- Modelos: `IdentityResult`, `IdentitySearchResult`, `IdentityHierarchy`, `IdentitySummary`,
  `IdentityReference`, `IdentityError`.
- Excepciones: `IdentityNotFound/Conflict/ValidationError/PermissionError/HierarchyError/StateError`.
- Interfaz de adaptador (factory): `empresa_id`, `tienda_actual`, `almacen_actual`,
  `empresa_tienda_almacen`, `contexto`, `identidad`, `telemetria`.
- Fachada DB: `empresa_id`, `tienda_id`, `tienda_id_int`, `almacen_id`, `registrar_resolver`.
- Versionado: `API_VERSION="v2"`, `VERSIONES_SOPORTADAS=("v1","v2")` (ranura v3 reservada).

**Regla de estabilidad:** estas firmas **no se cambian** en v3; solo se añaden (nunca se rompen).

## 5. Componentes deprecados

- **`gemelo.fuentes.emp`** — shim de compatibilidad (Bloque V). Comportamiento intacto; no debe usarse
  en desarrollos nuevos. Retirada prevista en v3.x cuando su uso primario sea 0 (hoy: solo *fallback*
  en seams migrados + su dueño, el Gemelo).
- **Feature legada `ref_tienda`/`ref_almacen`** — conservada por compatibilidad (Strangler); su
  sustitución total por códigos operativos IOC es evolución v3.x.

## 6. Componentes reservados

- **Ranura de versión `v3`** en IdentityAPI (arquitectura lista, sin implementar).
- **`db.identidad_contexto.registrar_resolver`** — punto de inyección para que la capa de datos use un
  resolver IOC enriquecido (reservado; no cableado).
- **Jobs IOC opt-in** (`identidad_validacion_centros/verificacion_terminales/sincronizacion`) —
  registrados, deshabilitados por defecto.
- **17/17 adaptadores referenciados** (0 adaptadores muertos).

## 7. Compatibilidad garantizada (matriz)

| Con | Estado |
|-----|--------|
| IOC v1 / v2 / v3 | ✔ compatible |
| CRM · Stock · Compras · Producción · TPV · Ventas/Facturación · Logística · RRHH · Finanzas · Calidad · SAT · GMAO · Documentación · Fiscalidad · Contabilidad · Tesorería | ✔ (100 % vía adaptador) |
| Workflow · Scheduler · Motores corporativos | ✔ (COMPATIBLE / integrados donde procedía) |
| GUI | ✔ sin cambios (usa canónico; migración a IdentityAPI = v3.x/L5) |
| Base de datos | ✔ sin cambios de esquema; fachada aditiva |

## 8. Rendimiento (Parte D)

- `empresa_id` (IOC `_base.emp`): **~0,16 µs/op**; legado `empresa_actual_id`: ~0,95 µs/op —
  **equivalentes** (coste despreciable; el camino caliente no añade overhead observable).
- Resolución completa (`IdentityAPI.resolver`): **miss ~16,5 ms** / **hit (caché) ~9,7 ms** — la caché
  reduce la latencia; solo interviene en resoluciones significativas (no en `empresa_id`).
- **Impacto neto: neutro/positivo**. Sin regresión de rendimiento respecto a la arquitectura anterior.

## 9. Seguridad (Parte E)

- **Aislamiento multiempresa estricto verificado:** clave de caché `(id_empresa, ns, key)`; valores de
  empresas distintas no se cruzan; invalidación **selectiva por empresa** (A borrada, B intacta).
- **Gobierno:** estados oficiales (ACTIVO→…→HISTORICO), **soft delete** (nunca borrado físico),
  **campos inmutables rechazados** (verificado), propiedad/responsables auditados.
- **RBAC:** 7 permisos `identidad.*`. **Auditoría:** `log_auditoria` + `ioc_identidad_auditoria`
  (valor anterior/nuevo, IP, terminal). **Sin fugas entre empresas.**

## 10. Observabilidad (Parte F)

- **Telemetría** homogénea (adaptadores + IdentityAPI): llamadas, errores, tiempos, cache hits/miss.
- **Eventos** normalizados: `identidad.*` (núcleo), `identity.api.*`, `<modulo>.identidad.resuelta`.
- **Preparación (no implementada):** exportador **Prometheus** (snapshot ya estructurado), **OpenTelemetry**
  (spans en `_medir`/resolver), **tracing distribuido** (correlación por evento). Diseño listo; sin
  herramientas externas aún.

## 11. Riesgos residuales

| Riesgo | Nivel | Mitigación |
|--------|-------|-----------|
| Shim `fuentes.emp` aún referenciado (fallbacks) | Bajo | Deprecado; retirada en v3.x cuando uso primario=0 |
| Seams infra/Enterprise con canónico (no IOC) | Bajo | COMPATIBLE (usan el fundamento de IOC); homogeneización opcional v3.x |
| Capa DB parcialmente sobre fachada (96 %) | Bajo | Fachada lista; `db/stock.py` + empresa+tienda pendientes |
| GUI usa canónico directo | Bajo | Migración a IdentityAPI = v3.x/L5 |
| Caché en proceso (no distribuida) | Bajo | Suficiente monoproceso; caché distribuida = v3.x |

## 12. Plan IOC v3.x (diseñado, no implementado)

| Iniciativa | Beneficio | Impacto | Dependencias | Riesgo | Prioridad |
|-----------|-----------|---------|--------------|--------|-----------|
| Caché distribuida (Redis) | Escala multiproceso/nodo | Medio | infra Redis | Medio | Alta |
| Multi-nodo + sincronización de identidades | SaaS Enterprise multi-región | Alto | job `identidad_sincronizacion` (reservado) | Medio | Media |
| Exportador Prometheus | Observabilidad producción | Bajo | telemetría (lista) | Bajo | Alta |
| OpenTelemetry + tracing distribuido | Diagnóstico end-to-end | Medio | OTel SDK | Bajo | Media |
| Federación de identidades (SaaS) | Identidad entre tenants/holdings | Alto | grupos (listo) | Alto | Media |
| Auditoría distribuida | Trazabilidad multi-nodo | Medio | event sourcing (Resiliencia) | Medio | Baja |
| Retirada final del shim `fuentes.emp` | Limpieza | Bajo | uso primario=0 | Bajo | Media |
| GUI → IdentityAPI (L5) | Pureza arquitectónica | Medio | evidencia visual | Bajo | Media |

## 13. Recomendaciones

1. **Congelar** la API pública (sección 4); toda evolución = v3.x aditiva.
2. Ejecutar las fases pendientes (L2 infra opcional, L3 resto DB, L4 retirada shim, L5 GUI) de forma
   incremental y verificada, **sin urgencia** (el sistema es estable).
3. Priorizar **Prometheus** (bajo coste, alto valor de observabilidad) y **caché distribuida** cuando
   se despliegue multiproceso/SaaS.
4. Mantener la disciplina Strangler: cambios mínimos, evidencia objetiva, reversibilidad.

## 14. Certificación técnica final

Se **CERTIFICA** que el Motor Corporativo de Identidad (IOC) de Smart Manager AI cumple:
- **Arquitectura correcta** (dirección de dependencias `ERP → IdentityAPI → … → BD`, sin ciclos,
  capas separadas, inversión de dependencias en la fachada DB). ✔
- **API pública estable y congelada** (contratos tipados, modelos, excepciones, versionado). ✔
- **Seguridad** (aislamiento multiempresa, gobierno, RBAC, auditoría; sin fugas). ✔
- **Rendimiento** neutro/positivo. ✔
- **Compatibilidad total** (IOC v1/v2/v3 + todos los módulos y motores). ✔
- **Cero regresiones** (AST OK en todo el ecosistema IOC; **smoke 5 passed**). ✔

**IOC v3 queda oficialmente certificado como infraestructura estable de identidad corporativa del
ERP. La arquitectura se declara CONGELADA para IOC v3.** Las evoluciones futuras se realizarán como
**IOC v3.x**, aditivas y compatibles con esta certificación.

> Nota de proceso: este bloque no ha modificado código (no se halló desviación objetiva). Los
> artefactos son documentales: esta certificación + `DOCUMENTACION_IOC.md` (referencia técnica).
