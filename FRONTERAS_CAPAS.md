# FRONTERAS_CAPAS.md — Fronteras entre capas

Fecha 2026-07-30. Define qué puede y qué NO puede asumir cada capa, y qué dependencias son válidas. Incluye la
**Detección de importaciones cruzadas** reales (Objetivo 8). Solo documentación; nada se corrige aquí.

## Capas y responsabilidades

### `db/` (acceso a datos)
- **SÍ**: SQL, esquema (`conexion.ensure_schema`), CRUD, `log_auditoria`, aislamiento por `id_empresa`.
- **NO** (ideal): lógica de negocio compleja, orquestación de dominio, UI.
- **Dependencias válidas**: `db.conexion`, `db.empresa`, otros `db.*`. **Inválidas (ideal)**: `services.*`,
  `gui.*`.

### `services/` (dominio/lógica)
- **SÍ**: reglas de negocio, orquestación, composición de infra (RBAC/Entitlements/Event Bus/Storage).
- **NO**: SQL directo cuando exista un `db.*`; UI (`gui.*`).
- **Dependencias válidas**: `db.*`, otros `services.*`, `utils`, `sdk`. **Inválidas**: `gui.*`.

### `gui/` (escritorio PyQt6)
- **SÍ**: presentación, orquestación de interfaz, señales/slots.
- **NO**: lógica de negocio (debe vivir en `services/`).
- **Dependencias válidas**: `services.*`, `gui.components`, `gui.foundation`, `utils`. **Tolerado histórico**:
  `db.*` directo (desktop legacy). **Inválidas**: que `services/`/`db/` dependan de `gui/`.

### `backend/` + `api/` (REST/HTTP)
- **SÍ**: enrutado, auth (JWT), serialización; SOLO consume `services/` (API-First).
- **NO**: BD directa, lógica de negocio. **Válidas**: `services.*`, `api.security`. **Inválidas**: `gui.*`.

### `portal_web/` (Back Office web)
- **SÍ**: navegación/acceso/layout componiendo `services/`+RBAC+Entitlements. **NO**: negocio propio, permisos
  propios, BD directa. **Válidas**: `services.*`, `api.security`. **Inválidas**: `gui.*`, duplicar reglas.

### `marketplace/` · `comercio_digital/` (dominios)
- Son `services/*`: aplican sus reglas. **Válidas**: `db.*`, otros `services.*`, `sdk`. **Inválidas**: `gui.*`.
- Frontera de responsabilidad: ver ARQUITECTURA_DOMINIOS.md (Canal Web ≠ Marketplace ≠ Catálogo).

### `platform/` (prep. microservicios)
- Infra de plataforma (registry/discovery/gateway…). Latente. **NO** debe acoplar dominios hasta activarse.

## Detección de importaciones cruzadas (evidencia real)

| Cruce | Nº | Naturaleza | Veredicto |
|---|---|---|---|
| `db/ → services.*` | **30** | Casi todo = `services.eventos` (publicar eventos) por **import PEREZOSO** dentro de funciones + `contabilidad.posting` | Inversión de capa **desacoplada por lazy import** (no rompe carga). Documentar; revisar a futuro |
| `services/ → gui.*` | **1** | `services/tpv/extras_precios.py` importa `gui.tpv._EXTRAS_TPV` | **Violación real** de capa (servicio depende de UI). Documentar; corregir a futuro |
| `db/ → gui.*` | 2 | puntuales | Violación menor. Documentar |
| `gui/ → db.*` (directo) | **59 ficheros** | La GUI de escritorio consulta BD saltándose `services/` | **Patrón histórico** del desktop; tolerado. A futuro, encaminar por `services/` en las pantallas que se reescriban |

> **Imports circulares**: no se detectan ciclos "duros" en carga (los cruces `db→services` usan lazy import,
> que es el mecanismo habitual para evitar ciclos). **Recomendación**: confirmar objetivamente con
> `import-linter`/`pydeps` en una tarea de tooling (no realizada aquí para no tocar el proyecto).

## Reglas de frontera (para futuras fases)

1. `db/` no importa `services/` salvo publicación de eventos por lazy import (tolerado, marcar como excepción).
2. `services/` **nunca** importa `gui/` (corregir el único caso `tpv/extras_precios`).
3. `gui/` nuevo consume `services/` (no `db/` directo).
4. `api/`/`portal_web/` solo `services/` (API-First).
5. El **núcleo** (`db.conexion`/`db.empresa`/`seguridad`/`observabilidad`/`saas`/`eventos`) no depende de
   dominios de negocio.
