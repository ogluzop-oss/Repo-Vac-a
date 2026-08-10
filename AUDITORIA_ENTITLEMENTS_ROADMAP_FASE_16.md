# AUDITORÍA — ENTITLEMENTS SaaS (Roadmap Fase 16) (Fase 14)

Fecha 2026-07-27. Read-only. **NO se implementa la Fase 16.** Sólo se audita si la arquitectura actual la
soporta y si existe el anti-patrón de gating disperso.

## Hallazgo clave: NO hay gating disperso

- `grep "plan == 'PRO'|'PLUS'|'BASIC'"` en `src/` → **0 coincidencias**. No existe el anti-patrón
  `if plan == "PRO"` repartido por la aplicación.
- El control de plan ya está **centralizado** en `services/saas`:
  - `licensing.modulo_habilitado(modulo, id_empresa)` — capacidad por módulo.
  - `licensing.limite_disponible(recurso, id_empresa)` — límites/cuotas.
  - `licensing.validar_operacion(modulo=, recurso=, id_empresa=)` — resolución combinada.
  - `enforcement.exigir_modulo` / `enforcement.acceso_modulo(v_id)` / `enforcement.nivel_acceso`.
  - `planes.py` (definición de planes), `suscripciones.py`, `metricas.py`, `dunning.py`.
- Los consumidores llaman al resolver (`licensing.`/`enforcement.`), no comparan el plan directamente
  (p. ej. `cloud_manager`, `saas_global`, `tpv/refund_service`).

## Encaje con el modelo objetivo Fase 16

`Plan → Entitlement Resolver → Capability → Policy/Limit → Feature`

| Elemento objetivo | Base actual | Encaje |
|---|---|---|
| Plan | `saas/planes.py` + `suscripciones` | 🟢 |
| Entitlement Resolver | `licensing.validar_operacion`/`modulo_habilitado`/`limite_disponible` | 🟢 (evolucionable a `capability`) |
| Capability | `modulo` (hoy por módulo) | 🟡 (ampliar a claves finas `tpv.avanzado`, `ia.forecasting.ml`, …) |
| Policy / Limit | `limite_disponible` (recursos/cuotas) | 🟢 |
| Feature gate | `enforcement.exigir_modulo`/`acceso_modulo` | 🟢 |

## Capacidades objetivo (preparación)

`tpv.avanzado`, `ia.forecasting.ml`, `ia.retraining`, `multi_tienda.enabled`, `storage.s3`,
`correo.buzones.max`, `usuarios.max`, `tiendas.max`, `almacenes.max`, `api.access`, `realtime.distributed`,
`mobile.app` → se mapean sobre el resolver existente añadiendo un **catálogo de capabilities** y su
resolución por plan (sin tocar los consumidores, que ya llaman al resolver central).

## Dependencias/roces a resolver en Fase 16 (no ahora)

1. Ampliar el resolver de "módulo" a **capabilities finas** (namespacing `dominio.capacidad`), manteniendo
   compatibilidad con `modulo_habilitado`.
2. Un **catálogo declarativo** de capacidades↔plan (evitar lógica imperativa).
3. Puntos que hoy consultan `modulo_habilitado` por nombre de módulo deberían migrar a `capability()` de forma
   gradual (Strangler), sin romper compatibilidad.
4. Cache del resolver por tenant (rendimiento) reutilizando el patrón existente.

## Veredicto

🟢 **La arquitectura actual SOPORTA la Fase 16** sin refactor disruptivo: ya existe un resolver central de
licencias/enforcement y **0 gating disperso**. La Fase 16 evoluciona (no reemplaza) `services/saas` hacia
capabilities finas. 🔵 preparado; implementación diferida (roadmap).
