# INFORME FINAL — FASE 16 · Entitlements / Capabilities SaaS

Fecha 2026-07-29. Evolución del licenciamiento hacia un resolver central de capacidades/cuotas. N7 (sin motor
paralelo), sin AWS, sin despliegue, sin costes.

## Cambios realizados

| Fichero | Cambio |
|---|---|
| `src/services/saas/entitlements.py` | **NUEVO** — resolver central: matriz BASIC/PRO/PLUS, `has/can/limit/require/estado_cuota/puede_crear/plan_actual/snapshot/matriz`, PLUS ilimitado, OVER_LIMIT, auditoría |
| `src/services/saas/licensing.py` | **MODIF** — `validar_operacion(..., capability=)` + fachadas `capability_habilitada`/`estado_cuota` (delegan en entitlements). APIs antiguas intactas |
| `tests/unit/test_entitlements.py` | **NUEVO** — 12 tests (BASIC/PRO/PLUS, legacy, OVER_LIMIT, require/audit, multi-tenant, backward-compat) |
| `AUDITORIA_ENTITLEMENTS_FASE_16.md` | **NUEVO** — auditoría previa |

**Tablas nuevas: 0** (la matriz vive en código; la licencia sigue en `empresa_licencia`). **Migraciones: 0.**

## Arquitectura de Entitlements

`PLAN → ENTITLEMENTS → CAPABILITIES → OPERACIONES`. Los módulos consultan capacidades, **nunca el plan**
(`if plan == "PRO"` prohibido y ausente). Resolución **multi-tenant** por `id_empresa` (reutiliza
`licensing.licencia_activa`/`_contar`). Entitlements ≠ RBAC: coexisten (RBAC = usuario; entitlements = tenant).

- **Booleanas** (`has`): capacidad disponible o no.
- **Cuotas** (`limit`/`estado_cuota`/`puede_crear`): límite numérico + estado `OK/AT_LIMIT/OVER_LIMIT`.
- **`require(cap)`**: enforcement ANTES de la operación (nunca a mitad de un flujo) → `LicenciaError` +
  auditoría `ENTITLEMENT_DENIED` si no procede.

## Matriz final BASIC / PRO / PLUS

| Capability | BASIC | PRO | PLUS |
|---|---|---|---|
| tpv.avanzado | ❌ | ✅ | ✅ |
| ia.forecasting.ml | ❌ | ✅ | ✅ |
| ia.retraining | ❌ | ❌ | ✅ |
| multi_tienda.enabled | ❌ | ✅ | ✅ |
| storage.s3 | ❌ | ✅ | ✅ |
| api.access | ❌ | ✅ | ✅ |
| realtime.distributed | ❌ | ✅ | ✅ |
| mobile.app | ❌ | ❌ | ✅ |
| usuarios.max | 5 | 50 | ∞ (unlimited) |
| tiendas.max | 1 | 10 | ∞ |
| almacenes.max | 1 | 50 | ∞ |
| correo.buzones.max | 1 | 10 | ∞ |

**PLUS = acceso total** (todas las booleanas True; todos los límites `UNLIMITED = None`). **Legacy (sin
licencia) = PLUS** (comportamiento actual intacto). `BLOQUEADO` (suspendida/cancelada) → todo False / límite 0.

## Capacidades y límites implementados

- 8 capacidades booleanas + 4 cuotas (arriba). Ampliable editando `_MATRIZ` (fuente única; sin tocar módulos).
- **Downgrade no destructivo**: si el uso supera el nuevo límite → `OVER_LIMIT`; se bloquea SOLO crear nuevos;
  los recursos existentes se conservan y se pueden editar/eliminar. Entitlements es **solo lectura** (nunca
  borra ni modifica datos).

## Puntos de enforcement

- Central, reutilizable y **opt-in** (backend): `licensing.validar_operacion(capability=)` y
  `entitlements.require/can/has/limit/estado_cuota/puede_crear`.
- **No se reescribió ningún módulo funcional** (TPV/Stock/Caja/CRM/RRHH/Finanzas/Logística intactos — sección
  18). La UI puede consultar `snapshot()`/`has()` para mostrar/deshabilitar, pero el enforcement real vive en
  backend. Los flujos operativos principales de BASIC/PRO siguen completos de principio a fin.

## Tests ejecutados y regresión

- `tests/unit/test_entitlements.py`: **12 passed** (matriz/PLUS ilimitado, BASIC, PRO, legacy, OVER_LIMIT,
  estado_cuota solo-lectura, require+deny, multi-tenant aislado, backward-compat, validar_operacion(capability),
  snapshot).
- Regresión completa: **681 passed, 1 skipped, 0 failed** (baseline 669 → +12). **0 regresiones.**
- APIs antiguas (`modulo_habilitado`/`limite_disponible`/`validar_operacion`) verificadas intactas.

## Confirmaciones obligatorias

- ✅ **AWS NO ha sido desplegado.** No se ejecutó `terraform apply/destroy/import`, ni AWS CLI de creación, ni
  `cdk deploy`, ni `docker push`.
- ✅ **No se generaron costes AWS.** Todos los `enable_*` siguen en `false`; la IaC de `infra/aws` permanece
  intacta y preparada.
- ✅ La aplicación funciona en modo local sin dependencia de AWS (RDS/S3/Redis/SQS/ECS/Secrets Manager).
- ✅ 0 gating disperso `if plan ==` (regla de oro respetada).
- ✅ 0 tablas/migraciones nuevas; APIs antiguas sin romper; downgrade no destructivo.

## Criterios de finalización (23) — cumplidos

Resolver central ✅ · módulos consultan capabilities/cuotas ✅ · BASIC restringido ✅ · PRO profesional ✅ · PLUS
total ✅ · límites centralizados ✅ · multi-tenant seguro ✅ · APIs antiguas ok ✅ · auditoría de denegaciones ✅ ·
tests sin regresiones ✅ · AWS sin desplegar ✅ · sin costes ✅ · sin despliegue ✅ · IaC preparada intacta ✅.

**FASE 16 COMPLETADA. Me detengo: no avanzo a Fase 15, no despliego AWS, no activo recursos.**
