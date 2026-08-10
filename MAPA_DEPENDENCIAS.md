# MAPA_DEPENDENCIAS.md — Mapa global de dependencias

Fecha 2026-07-30. Generado por conteo de imports reales (`grep from src...`). Guía para futuras
simplificaciones. Solo lectura.

## Núcleo (core) — alto fan-in, todos dependen de ellos

| Módulo | Imports entrantes | Rol |
|---|---|---|
| `db.conexion` | **881** | Pool/BD/`ensure_schema`/`log_auditoria` — cimiento absoluto |
| `db.empresa` | **326** | Tenant (`empresa_actual_id`/`tienda_actual_id`) — cimiento multi-tenant |
| `db.usuario` | 65 | Usuarios/sesión |
| `services.seguridad` | 53 | MFA/secret_manager/tenant_guard |
| `services.observabilidad` | 49 | logs/health/métricas |
| `services.saas` | 42 | licensing/entitlements |
| `db.identidad_contexto` | 24 | contexto IOC |

> Regla: el núcleo (`db.conexion`, `db.empresa`, `seguridad`, `observabilidad`, `saas`) NO debe depender de
> dominios de negocio. Es la base sobre la que todo se apoya.

## Dominios de alto fan-in (grandes, muy consumidos)

| Dominio | Imports entrantes | Naturaleza |
|---|---|---|
| `services.comercio_digital` | **152** | Plataforma comercial (canal web/checkout/pagos/envíos/sync…) |
| `services.tpv` | **101** | Punto de venta (báscula/pagos/pasarela/canal…) |
| `services.identidad` | 92 | IOC (centros/terminales/impresoras) |
| `services.gemelo` | 79 | Gemelo Digital (estado vivo, fuente para IA) |
| `services.fiscal` | 72 | Verifactu/Facturae/mTLS AEAT |
| `services.prediccion` | 47 | Motor predictivo |
| `services.ccp` | 47 | Comunicaciones corporativas |
| `services.contabilidad` | 42 | Contabilidad PGC |

## Dependencias fuertes (estructurales, difíciles de romper)

- **Todo → `db.conexion` / `db.empresa`** (881/326): acoplamiento inevitable y sano (cimiento).
- **`gui/*` → `db/*` directo** (59 ficheros): la GUI de escritorio consulta BD sin pasar por `services/`
  (patrón histórico del desktop). Fuerte y transversal.
- **`services.eventos`/`eventbus`** como bus central (fan-out a suscriptores) — acoplamiento por eventos (débil
  en compilación, fuerte en runtime).

## Dependencias débiles (desacoplables, lazy)

- **`db/* → services.eventos`** (30, imports PEREZOSOS dentro de funciones): publicación de eventos desde la
  capa de datos → invertida pero desacoplada por lazy import.
- Composiciones de las capas nuevas (`portal_web.acceso → entitlements/licensing/autorizacion`;
  `canal_web → conexiones/publicaciones`) — por fachada, sustituibles.

## Módulos núcleo vs periféricos

- **Núcleo**: `db.conexion`, `db.empresa`, `seguridad`, `autorizacion`, `saas`, `observabilidad`, `eventos`/
  `eventbus`.
- **Semi-núcleo (hubs de dominio)**: `comercio_digital`, `tpv`, `identidad`, `gemelo`, `fiscal`, `prediccion`.
- **Periféricos** (bajo fan-in, hojas): `portal_web`, `marketplace.integraciones_comerciales`,
  `camaras`, `rfid`, `mobile`, `datalake`, `bpd`, `simulador`, `autonomia`.

## Grafo (resumen conceptual)

```
gui/*  ─┬─▶ services/* ─┬─▶ db/* ──▶ db.conexion / db.empresa   (cimiento)
        └─▶ db/* (directo, 59 ficheros — desktop legacy)
services.eventbus ─(fachada)─▶ services.eventos ─(bus)─▶ suscriptores (realtime/SSE, jobs, dominios)
db/* ─(lazy)─▶ services.eventos            (inversión desacoplada)
```

## Recomendación
Para futuras simplificaciones, atacar primero lo **periférico** (bajo fan-in) y usar el **núcleo** como
frontera estable. Confirmar ausencia de ciclos con una herramienta de grafos (`import-linter`/`pydeps`) — ver
DETECCIÓN en la sección de importaciones cruzadas (GUIA / este mapa).
