# AUDITORÍA — FASE WEB-09 · Back Office Web para Empleados (Portal Web)

**Fecha:** 2026-07-30 · **Tipo:** desarrollo de UI como VISTA sobre servicios existentes (N7; sin lógica
nueva, sin duplicar servicios/reglas, sin segunda app). **Regresiones:** 0 · **Suite:** 710 → **714
passed, 1 skipped** (+4 tests WEB-09).

## Objetivo

Evolucionar el Portal Web de "shell" a Back Office web real: 8 secciones que **solo presentan** datos
reutilizando `services/*` / `db/*` existentes, con navegación fluida (lazy loading) y componentes
reutilizables. Todo degradable.

## Estructura creada (área Portal Web — no toca dominios prohibidos)

`src/gui/portal_web_ui/` (paquete nuevo):

| Fichero | Sección | Servicios reutilizados (N7) |
|---|---|---|
| `componentes.py` | Componentes reutilizables | `KpiCard`, `TablaDatos`, `Buscador`, `Toolbar`, `Breadcrumb`, `PanelSeccion` (+ `gui/_neon_ui`) |
| `inicio.py` | **Inicio** (dashboard) | `online_orders_service.facturacion_por_dia`/`listar_pedidos_online`/`listar_reservas`; `db.reabastecimiento.listar_propuestas` (stock crítico); `services.notificaciones` (avisos/incidencias) |
| `reservas.py` | **Reservas** | `online_orders_service.listar_reservas`/`cambiar_estado_reserva` (→ `db.catalogo`) |
| `encargos.py` | **Encargos** | **reutiliza `SeccionReservas`** con `TIPO="ENCARGO"` (no hay motor separado de encargos) |
| `stock.py` | **Stock** (solo consulta) | `db.stock_almacen.listar_almacenes`/`obtener_stock_almacen`/`stock_total_global`; `db.kardex.historial_articulo` |
| `clientes.py` | **Clientes** (CRM) | `db.clientes.buscar_clientes`/`listar_clientes`/`obtener_cliente`/`historial_comercial` |
| `logistica.py` | **Logística** | accesos rápidos (arquitectura preparada; sin implementar — Sección 7) |
| `configuracion.py` | **Configuración** | reutiliza `gui/canal_web_config.CanalWebConfigDialog` (Canal Web, ya NO el TPV) |

`src/gui/portal_web_gui.py` (`PortalWebWindow`): pasa de shell placeholder a **shell de navegación con lazy
loading** — barra lateral de 8 secciones + `QStackedWidget`; cada sección se crea la primera vez que se
visita (`_crear_seccion` factory + `_cache`). Pantalla inicial = **Inicio** (dashboard). Pedidos Online =
`PortalWebHome` (núcleo WEB-08). Navegación fluida en una sola ventana (sin abrir ventanas innecesarias).

## Reutilización estricta (N7) — la UI NO implementa lógica

- Ninguna sección abre conexión ni ejecuta SQL (verificado por test: sin `obtener_conexion`/`cursor(`).
- Todo dato proviene de servicios/db existentes; multiempresa/multitienda y RBAC se resuelven DENTRO de
  esos servicios (contexto de sesión/tenant), no en la vista.
- No se creó "Smart Stock Web" (Stock reutiliza Smart Stock), ni "CRM Web" (Clientes reutiliza `db.clientes`),
  ni un motor de encargos (Encargos = Reservas tipo ENCARGO), ni se volvió al TPV para la config (Canal Web).
- Auditoría: se mantiene la existente (los cambios de estado de reserva ya auditan en `online_orders_service`).
  No se crearon eventos nuevos.

## Componentes reutilizables (preparados para fases futuras)

`KpiCard` (tarjetas KPI), `TablaDatos` (tabla neón `cargar(cols, filas)`), `Buscador` (señal `buscar`),
`Toolbar` (barra de acciones), `Breadcrumb` (migas de pan), `PanelSeccion` (base: breadcrumb+título+toolbar+
cuerpo+estado vacío). Reutilizan las primitivas de `gui/_neon_ui` (creadas en WEB-08).

## Responsive

Layouts con políticas expansivas (sidebar fija + contenido expansible, tablas `Stretch`) → escritorio /
portátil / tablet. App móvil: fase posterior (no desarrollada).

## No modificado (PROHIBIDO)

Marketplace · Canal Web (servicios y `canal_web_config` solo se REUTILIZAN) · Portal Cliente · TPV · Caja ·
Facturación · RRHH · Producción · GMAO · SAT · AWS · Terraform · Docker · Entitlements · RBAC · Licencias
SaaS: **intactos**.

## Verificación / pruebas

- `test_web09_portal_web_backoffice.py` (4): cada sección instancia offscreen; el shell navega con lazy
  loading por las 8 secciones (Inicio inicial, Pedidos=PortalWebHome); componentes reutilizables;
  sin duplicación (Encargos⊂Reservas, Configuración⊂Canal Web) y sin SQL en las vistas.
- `test_web07`/`test_web08` verdes (WEB-08 actualizado al nuevo shell WEB-09).
- **Suite completa:** 714 passed, 1 skipped (0 regresiones sobre 710).

## Confirmaciones (pruebas del enunciado)

- [x] Navegación (fluida, lazy, 8 secciones, una sola ventana). [x] Reutilización de servicios (solo
  vistas). [x] Sin duplicación. [x] Sin regresiones. [x] Multiempresa/multitienda (resuelto en servicios).
  [x] Permisos (RBAC en servicios). [x] Auditoría (existente, sin eventos nuevos).

## Preparado para siguientes fases

Reservas/Encargos con crear/editar completos, Stock con movimientos avanzados, Clientes con acciones CRM,
Logística funcional (picking/expediciones/devoluciones/incidencias) y app móvil — todo reutilizando los
servicios ya conectados aquí.
