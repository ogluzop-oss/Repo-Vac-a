# IOC v3 — BLOQUE VI: Adopción transversal de IOC en los motores corporativos

> Bloque de **auditoría y verificación**. Solo se ha intervenido en los motores cuya auditoría
> demostró **objetivamente** uso del mecanismo heredado (`fuentes.emp`, deprecado en Bloque V). El
> resto se documenta como YA COMPATIBLE o NO APLICA, **sin tocarlo**. Sin migraciones, sin nuevas
> capas, sin adaptadores innecesarios. Verificado; smoke 5 passed; cero regresiones.

## Criterio de decisión (objetivo)

- **REQUIERE ADOPCIÓN** → el motor resuelve identidad con el **shim deprecado `fuentes.emp`**.
- **COMPATIBLE** → el motor resuelve con el **canónico `empresa_actual_id`** (conservado en Bloque V
  como fundamento de IOC) o **ya consume IdentityAPI/adaptador**. No se modifica (sin beneficio real).
- **NO APLICA** → el motor **no resuelve identidad**.

## 1. Motores auditados (clasificación)

| Motor | Ubicación | ¿Resuelve identidad? | Cómo | Clasificación |
|-------|-----------|----------------------|------|---------------|
| Workflow | `services/workflow` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| Scheduler (motor) | `services/scheduler.py` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| Scheduler (registry) | `services/scheduler_registry.py` | No | — (usa IOC en jobs) | **NO APLICA** |
| Automatizaciones | `services/automatizacion` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| Actividad | `services/actividad` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| Gobierno | `services/gobierno` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| **Seguridad** | `services/seguridad/password_politica.py` | Sí | **`fuentes.emp`** | **REQUIERE ADOPCIÓN → integrado** |
| **BI** | `services/bi/suscripciones.py` | Sí | **`fuentes.emp`** | **REQUIERE ADOPCIÓN → integrado** |
| BI Corporativo | `services/bi_corp` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| Copilot | `services/copilot` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| IA | `services/ia` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| Predicción | `services/prediccion` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| **Gemelo Digital** | `services/gemelo` | Sí | `fuentes.emp` (**es su dueño**) | **COMPATIBLE (dueño del shim)** |
| Distribución | `services/distribucion` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| SaaS | `services/saas` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| DR | `services/dr` | No | — | **NO APLICA** |
| Resiliencia | `services/resiliencia` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| Agentes | `services/agentes` | Sí | (contexto) | **COMPATIBLE** |
| Sync Transport | `services/sync_transport` | Sí | `empresa_actual_id` | **COMPATIBLE** |
| **Autonomía** | `services/autonomia/modos.py` | Sí | **`fuentes.emp`** | **REQUIERE ADOPCIÓN → integrado** |
| **Simulador** | `services/simulador/base.py` | Sí | **`fuentes.emp`** | **REQUIERE ADOPCIÓN → integrado** |
| Webhooks/Tareas/Mensajería/Notificaciones/Eventos | `services/*` | Sí (menor) | `empresa_actual_id` | **COMPATIBLE** |
| Event Bus | `services/eventos` | No (transporta) | — | **NO APLICA (identidad)** |

## 2. Motores compatibles (no modificados)

Workflow, Scheduler (motor), Automatizaciones, Actividad, Gobierno, BI Corporativo, Copilot, IA,
Predicción, Distribución, SaaS, Resiliencia, Agentes, Sync Transport, Webhooks, Tareas, Mensajería,
Notificaciones, Event Bus. **Motivo:** usan el resolutor canónico `empresa_actual_id` (conservado en
Bloque V como fundamento de IOC) o ya consumen IOC. Migrarlos añadiría una capa sin beneficio
arquitectónico real → **no se tocan** (regla del bloque).

## 3. Motores integrados (intervención mínima)

**4 motores** cuyo `_emp` usaba el shim **deprecado** `fuentes.emp` → ahora resuelven vía IOC
(`identidad._base.emp`), con `fuentes.emp` **solo como fallback**:
- `services/seguridad/password_politica.py`
- `services/bi/suscripciones.py`
- `services/autonomia/modos.py`
- `services/simulador/base.py`

**Sin nuevos adaptadores ni capas** (regla «no crear adaptadores innecesarios»): se enruta al
resolutor canónico de IOC. Comportamiento **idéntico** verificado (`== fuentes.emp`).

## 4. Motores no aplicables

Scheduler Registry (orquesta jobs, no resuelve identidad; los jobs ya usan IOC), DR (no resuelve
identidad), Event Bus (transporta eventos). No requieren identidad propia.

## 5. Dependencias heredadas eliminadas

- 4 dependencias primarias del **shim deprecado `fuentes.emp`** eliminadas (pasan a fallback).
- **Gemelo Digital**: es el **dueño** de `fuentes.py`; su uso interno de `fuentes.emp` es su función
  nativa (retenida por diseño en Bloque V). **No se modifica** (sin beneficio real; evita riesgo en
  el motor del Gemelo, del que depende la IA).

## 6. Duplicidades detectadas

- Ninguna duplicidad nueva. Los motores COMPATIBLE comparten el canónico `empresa_actual_id` (fuente
  única). No hay reimplementaciones divergentes de identidad en los motores.

## 7. Riesgos

| Riesgo | Estado |
|--------|--------|
| Cambio de comportamiento en los 4 motores | Nulo (verificado `== fuentes.emp`) |
| Ciclo de importación (motor → IOC → gemelo) | Evitado: `identidad._base.emp` usa `db.empresa`, **no** importa gemelo |
| Tocar motores compatibles innecesariamente | Evitado (regla del bloque respetada) |
| Gemelo (dueño del shim) | No modificado; shim retenido por diseño |

## 8. Compatibilidad

IOC v1/v2, IdentityAPI, IdentityContext, Repository, Resolver, ValidationEngine, Cache, Scheduler,
Workflow, Seguridad, RBAC (7 permisos), Telemetría, Eventos, Multiempresa/Multitienda/SaaS:
**verificados y sin cambios**. Smoke **5 passed**. Regresiones **0**.

## 9. Rollback

- Reversible al 100 %: cada `_emp` migrado conserva `fuentes.emp` como fallback; revertir = restaurar
  el cuerpo anterior (marca `IOC v3 (Bloque VI)` localizable). Sin cambios de BD.

## 10. Estado final de IOC como servicio corporativo transversal

- **Todos los motores corporativos que resuelven identidad** lo hacen ahora mediante IOC o mediante el
  **resolutor canónico conservado** (fundamento de IOC): no queda ningún motor dependiendo del shim
  **deprecado** como mecanismo primario (salvo su dueño, el Gemelo, por diseño).
- IOC queda consolidado como **infraestructura de identidad transversal** del ERP: módulos funcionales
  (100 %) + capa de datos (fachada, 96 %) + motores corporativos que la necesitan.
- Estrategia Strangler **completamente reversible**; cambios mínimos y evidencia objetiva en cada
  intervención; cero modificaciones innecesarias.

### Anexo — Cambios de este bloque
- Integrados (routing a `identidad._base.emp`, fallback `fuentes.emp`): `seguridad/password_politica`,
  `bi/suscripciones`, `autonomia/modos`, `simulador/base`.
- No modificados (COMPATIBLE / NO APLICA / dueño del shim): el resto de motores auditados.
- Sin migraciones, sin nuevas capas, sin adaptadores nuevos, sin cambios de BD/GUI/SQL/modelos/
  permisos/auditoría.
