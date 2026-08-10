# INFORME — Portal Web para Empleados / Back Office (Fase WEB-04)

Fecha 2026-07-29. Nuevo módulo **`src/portal_web/`** (Back Office web para empleados), **independiente** del
Canal Web y del Portal Cliente, que **reutiliza** toda la lógica existente (N7). **Arquitectura PREPARADA**: sin
UI definitiva, sin APIs de negocio duplicadas, sin desplegar, sin coste. Regresión: **701 passed, 1 skipped**
(694 → +7).

## Cambios

| Fichero (nuevo salvo indicado) | Rol |
|---|---|
| `src/portal_web/__init__.py` | Fachada del módulo (descriptor + subcomponentes) |
| `src/portal_web/navegacion.py` | Registro DECLARATIVO de 13 secciones (sidebar/routing como datos); cada sección referencia módulo SaaS/capability y el SERVICIO existente que consume |
| `src/portal_web/acceso.py` | Decide secciones visibles COMPONIENDO Entitlements + licencia SaaS + RBAC + rol + tenant. **Sin permisos propios** |
| `src/portal_web/layout.py` | Contratos Layout/Sidebar/Navbar (datos, reutilizables por móvil) |
| `src/portal_web/sesion.py` | Reutiliza JWT/MFA/WebAuthn existentes (tenant del token; nunca dominio) |
| `src/portal_web/backend/rutas.py` | Rutas REST montadas en la API existente; reutiliza `requiere_auth` |
| `src/api/routers/portal.py` | Router DELGADO que delega en `portal_web` |
| `src/api/routers/__init__.py` | **(única modif. de existente)** añade `portal` a la lista de routers (aditivo) |
| `tests/unit/test_portal_web_web04.py` | 7 tests |

## Secciones (arquitectura preparada)

Inicio · Clientes · Artículos · Pedidos · Encargos · Reservas · Stock · Reabastecimiento · Logística · Caja
(sin TPV web) · RRHH · Documentos · Configuración. Cada una mapea al **módulo SaaS / capability** que la
habilita y al **servicio EXISTENTE** que consumirá (db.clientes, db.articulos/catalogo, services.ventas,
comercio_digital.pickup, db.kardex, services.reabastecimiento, db.logistica, db.caja, src.rrhh, db.documentos/
storage, db.empresa/usuario/rbac). **No duplica negocio.**

## Reutilización (N7 — nunca duplica)

- **RBAC** (`services.autorizacion.puede`), **Entitlements** (`saas.entitlements.has`), **licencia**
  (`saas.licensing.modulo_habilitado`) → `acceso` los compone; el Portal **no** define permisos.
- **JWT/MFA/WebAuthn** (`api.security.requiere_auth`, `seguridad.*`) → auth reutilizada; tenant del token.
- **API existente**: el router se monta en `/api/v1/portal/*` (mismo blueprint); NO se crea backend paralelo.
- Preparado para consumir **StorageProvider/SecretManager/auditoría/eventos** ya existentes.

## Endpoints REST (mínimos; sin duplicar negocio)

- `GET /api/v1/portal/live` (público) — módulo montado.
- `GET /api/v1/portal/descriptor` (público) — descriptor del módulo (sin datos).
- `GET /api/v1/portal/navegacion` (**JWT**) — layout+menú FILTRADO por RBAC/Entitlements/licencia/rol del
  usuario (tenant del token). Los datos de cada sección los sirven los routers/servicios ya existentes.

## Multi-tenant / móvil

- Todo por `id_empresa`/`id_tienda` (del token), **nunca por dominio**.
- Layout/sidebar/navbar como datos → **reutilizables parcialmente por la futura app móvil** (no implementada).

## Cumplimiento de restricciones

- **NO modificados**: Canal Web, Marketplace, Catálogo, TPV, Portal Cliente, Plugins, AWS, Terraform, Docker.
- **Sin** TPV Web / Caja Web / Pagos Online / Marketplace Web / Panel Cliente / sync AWS / tiempo real
  distribuido (solo arquitectura).
- **NO** se extrajo el Canal Web del TPV (explícitamente diferido a fase posterior).
- Sin despliegue, sin conexión de APIs externas, sin coste. Compatibilidad total (701 passed).

## Pendiente (fases futuras)

Frontend real (vistas/widgets), endpoints adicionales sólo si imprescindibles (reusar los existentes primero),
app móvil, y —cuando exista el Back Office completo— la extracción física del Canal Web fuera del TPV.

**FASE WEB-04 COMPLETADA. Portal Web (Back Office) preparado arquitectónicamente; 0 regresiones, 0 negocio
duplicado.**
