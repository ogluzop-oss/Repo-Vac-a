# AUDITORÍA — FASE WEB-11 · Logística operativa del Portal Web

**Fecha:** 2026-07-30 · **Tipo:** funcionalidad operativa como VISTA sobre servicios existentes (N7; sin
motores/tablas/modelos/servicios nuevos, sin SQL ni reglas en la UI). **Regresiones:** 0 · **Suite:** 720 →
**726 passed, 1 skipped** (+6 tests WEB-11).

## Objetivo

Convertir la sección Logística (placeholder desde WEB-09) en herramienta operativa completa reutilizando
`services/logistica/*`, `services/logistics/*` y servicios relacionados.

## Estructura (`src/gui/portal_web_ui/logistica.py`, reescrito)

`SeccionLogistica` = KPIs + sub-navegación interna (lazy) + panel de listado reutilizable `_PanelLista`
(filtro por estado + búsqueda + paginación + acciones + alta), todo con componentes existentes.

## Sub-áreas y servicios reutilizados (N7 — verificado en runtime)

| Sub-área | Operaciones | Servicio reutilizado |
|---|---|---|
| **Recepciones** | visualizar · buscar · filtrar | `services.logistics.logistics_service.listar_documentos_por_estado` (tipo recepción) |
| **Expediciones** | crear · confirmar · cerrar · cancelar · incidencia | `services.logistica.logistica_pro.expediciones`/`crear_expedicion`/`actualizar_seguimiento`/`registrar_incidencia_expedicion` |
| **Traspasos** | visualizar · seguimiento · estados · filtrar | `db.logistica.obtener_historial_traspasos` |
| **Picking/Packing** | listar (pendiente/en proceso/finalizado) · cerrar packing | `services.inventario.almacen_pro.listar_picking`/`cerrar_packing` |
| **Rutas/Entregas** | visualizar · estado · transportista | `services.crm.rutas.listar_rutas` |
| **Incidencias** | alta · resolución · seguimiento · histórico | `logistics_service.listar_incidencias`/`registrar_incidencia`/`cerrar_incidencia` |
| **Reabastecimiento** | visualizar propuestas · aceptar · rechazar · histórico | `db.reabastecimiento.listar_propuestas`/`cambiar_estado_propuesta` (sin algoritmo nuevo) |
| **Proveedores** | visualizar (ficha) | `db.proveedores.listar_proveedores` |
| **Stock** | tienda/almacén/reservado/tránsito/movimientos | **reutiliza `SeccionStock`** (Smart Stock; no duplica) |

**Persistencia real verificada (test DB):** crear expedición (1→2) vía `logistica_pro.crear_expedicion`.
La creación de incidencia con documento inexistente es RECHAZADA por el servicio (FK) — la UI delega la
validación en el servicio (N7), no la reimplementa.

## KPIs (Sección KPIs) — reutilizan datos existentes, sin recalcular

Recepciones pendientes · Expediciones pendientes · Picking pendiente · Incidencias abiertas · Pedidos en
tránsito (`online_orders` estado ENVIADO) · Reabastecimientos pendientes. Todos por conteo de los mismos
listados de servicio.

## Filtros / Buscador

- Filtro por **estado** (combo por sub-área, refetch al servicio) donde el servicio lo soporta
  (expediciones/picking/incidencias/reabastecimiento/traspasos/recepciones).
- Búsqueda + paginación + exportación en cada listado vía **`PanelTabla`** (cubre fecha/estado/cliente/
  proveedor/transportista/tienda/almacén/empleado/tipo por filtro textual unificado).
- **Buscador global** del Portal Web accesible desde la barra de la sección.

## Acceso a fichas (artículos/clientes/pedidos/proveedores/stock)

La sección navega a las secciones ya existentes del Portal Web mediante el callback `on_navegar` que cablea
el shell (`SeccionLogistica(on_navegar=self._navegar)`): Buscador · Clientes · Pedidos · Stock. Proveedores
tiene su propio sub-panel. **No se crean fichas nuevas** — se reutilizan las existentes.

## Componentes reutilizados (sin duplicar)

`KpiCard`, `PanelTabla`, `Toolbar`, `Buscador`, `Breadcrumb`, `PanelSeccion`, `FormPanel`. No se crearon
equivalentes. `_PanelLista` es un ensamblador de esos componentes, no un componente nuevo de presentación.

## Responsabilidades / multiempresa / auditoría

La UI solo muestra/edita/consulta/ejecuta acciones. Algoritmos, SQL, validaciones de negocio, RBAC,
auditoría y el aislamiento tenant (empresa/tienda/almacén desde sesión) viven DENTRO de los servicios. No se
crearon eventos nuevos. Verificado por test: la vista no contiene `obtener_conexion`/`cursor(`.

## No modificado (PROHIBIDO)

TPV · Canal Web · Marketplace · Portal Cliente · Catálogo · Facturación · Caja · RRHH · Producción · SAT ·
GMAO · AWS · Terraform · Docker · Entitlements · RBAC · Licencias SaaS: **intactos**. Único cambio fuera de
`portal_web_ui/logistica.py` = una línea en `portal_web_gui.py` (cablea `on_navegar`).

## Verificación / pruebas

- `test_web11_logistica.py` (6): navegación por 9 sub-áreas + KPIs; crear expedición (persiste);
  incidencias delega en servicio (FK); filtros por estado + buscador; acceso a fichas navega; sin
  duplicación (reutiliza componentes, sin SQL en la vista).
- **Suite completa:** 726 passed, 1 skipped (0 regresiones sobre 720).

## Confirmaciones (pruebas del enunciado)

- [x] navegación · [x] CRUD (expediciones/incidencias/reabastecimiento vía servicios) · [x] reutilización de
  servicios · [x] filtros · [x] buscador · [x] KPIs · [x] acceso a artículos/clientes/proveedores/pedidos
  (navegación a secciones existentes + sub-panel proveedores) · [x] ausencia de duplicación · [x] 0
  regresiones.
