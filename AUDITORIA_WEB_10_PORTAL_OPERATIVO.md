# AUDITORÍA — FASE WEB-10 · Portal Web operativo (CRUD reutilizando servicios)

**Fecha:** 2026-07-30 · **Tipo:** funcionalidad operativa como VISTA sobre servicios existentes (N7; sin
motores/servicios/lógica nuevos). **Regresiones:** 0 · **Suite:** 714 → **720 passed, 1 skipped** (+6
tests WEB-10).

## Objetivo

Convertir el Portal Web en herramienta de gestión diaria operativa: CRUD de reservas/encargos/clientes,
consulta avanzada de stock, pedidos, dashboard ampliado, buscador global, acciones rápidas y tablas
avanzadas — TODO reutilizando `services/*` / `db/*`. La lógica de negocio permanece en los servicios; la UI
solo captura y presenta.

## Secciones operativas (reutilización estricta — N7)

| Sección | Operaciones | Servicios reutilizados (verificado en runtime) |
|---|---|---|
| **Reservas** | crear · editar estado · confirmar · entregar · cancelar | `online_orders_service.reservar_articulo` / `cambiar_estado_reserva` / `listar_reservas` |
| **Encargos** | crear · editar · cambiar estado · **cerrar** · entregar · cancelar | **mismo motor**, tipo `ENCARGO` (`db.catalogo.crear_reserva(tipo="ENCARGO")` + `cambiar_estado_reserva`) — sin motor separado |
| **Clientes** | crear · editar · ficha (compras/reservas/encargos/incidencias) | `db.clientes.crear_cliente`/`actualizar_cliente`/`buscar_clientes`/`obtener_cliente`/`historial_comercial` + `online_orders`/`notificaciones` |
| **Stock** | consulta avanzada: búsqueda + filtros (almacén/tipo) + stock por almacén + movimientos + histórico (paginado/export) | `db.stock_almacen` + `db.kardex` — **SOLO CONSULTA** (no modifica/ajusta/inventaría) |
| **Pedidos Online** | aceptar/preparar/listo/entregar/cancelar | `PortalWebHome` (online_orders, WEB-08) |
| **Dashboard (Inicio)** | ventas·pedidos·reservas·encargos·stock crítico·**clientes nuevos**·**notificaciones**·avisos·incidencias | `online_orders_service`, `db.reabastecimiento`, `db.clientes`, `services.notificaciones` |
| **Buscador global** (nuevo) | clientes·artículos·pedidos·reservas·encargos en un punto | agrega los buscadores/listados existentes (`db.clientes`, `db.articulos`, `online_orders_service`) |

**Verificación de persistencia real (test DB):** crear cliente (22→23), crear reserva (0→1), crear encargo
tipo ENCARGO (0→1) a través de las secciones — todo vía servicios existentes.

## Componentes reutilizables (Secciones 10-11) — sin duplicar

- `TablaDatos` ampliado: **ordenación** por cabecera + **selección múltiple** + `filas_seleccionadas()`.
- **`PanelTabla`** (nuevo, reutilizable): búsqueda + paginación + **exportación** (reutiliza
  `gui.foundation.export.exportar_excel`, sin formato nuevo) + selección múltiple sobre `TablaDatos`.
- **`FormPanel`** (nuevo, reutilizable): formulario **INLINE** (no modal — respeta la lección SOMA de
  evitar modales en módulos con audio) para alta/edición; solo captura datos, la persistencia la hacen
  los servicios.
- Se siguen reutilizando `KpiCard`/`Buscador`/`Toolbar`/`Breadcrumb`/`PanelSeccion` (WEB-09).

## Navegación / acciones rápidas / breadcrumbs (Secciones 7-9)

- **9 secciones** en la barra lateral (se añade "Buscador global") con **lazy loading** y navegación fluida
  en una sola ventana.
- **Panel de acciones rápidas** (cabecera): Nuevo Cliente · Nueva Reserva · Nuevo Encargo · Buscar ·
  Pedidos · Reservas → navega a la sección y dispara su acción (`_accion_rapida`).
- **Breadcrumbs** en cada sección (`PanelSeccion.breadcrumb`), el usuario no pierde el contexto.

## Responsive (Sección 12)

Layouts con políticas expansivas (KPIs 4/fila, tablas `Stretch`, sidebar fija + contenido expansible) →
escritorio / portátil / tablet. Componentes preparados para reutilización en la futura app móvil.

## No modificado (PROHIBIDO)

TPV · Marketplace · Canal Web (servicios; `canal_web_config` solo se REUTILIZA) · Portal Cliente · Caja ·
Facturación · RRHH · AWS · Terraform · Docker · Entitlements · RBAC · Licencias SaaS: **intactos**.
Multiempresa/multitienda/RBAC/auditoría se resuelven DENTRO de los servicios (contexto de sesión/tenant),
no en la vista; no se crearon eventos nuevos.

## Verificación / pruebas

- `test_web10_portal_web_operativo.py` (6): crear reserva; crear encargo tipo ENCARGO; crear cliente;
  buscador global; componentes (PanelTabla paginación/filtro, FormPanel emite dict); shell 9 secciones +
  acciones rápidas abren el formulario de la sección.
- `test_web07/08/09` verdes (08/09 actualizados a la 9ª sección).
- **Suite completa:** 720 passed, 1 skipped (0 regresiones sobre 714).

## Confirmaciones (pruebas del enunciado)

- [x] creación/edición de reservas · [x] creación/edición de encargos · [x] consultas de stock (avanzada,
  solo consulta) · [x] consultas de clientes + CRUD · [x] buscador global · [x] navegación (fluida, lazy,
  breadcrumbs) · [x] componentes reutilizados (sin duplicados) · [x] sin duplicación · [x] sin regresiones.

## Preparado para siguientes fases

Modificación de reservas/encargos por campos (cuando exista servicio de update), acciones CRM avanzadas,
logística funcional (picking/expediciones/devoluciones/incidencias) y app móvil — reutilizando lo aquí
conectado.
