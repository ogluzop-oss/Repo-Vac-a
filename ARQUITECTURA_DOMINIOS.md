# ARQUITECTURA_DOMINIOS.md — Glosario oficial de dominios

Fecha 2026-07-30. **Documento de referencia** (Fase WEB-06). NO modifica código; fija la responsabilidad
canónica de cada dominio para evitar la "reconfusión" por nombres homónimos. Para cada dominio: objetivo ·
responsabilidades · qué NO hace · dependencias permitidas · dependencias prohibidas · módulo propietario.

> Regla transversal: la fuente ÚNICA de stock/precio es `articulos`; de marca web es `web_config`; de eventos
> es `services.eventos` (bus interno) con `services.eventbus` como fachada; de forecasting es
> `prediccion.forecasting`. Ningún dominio debe duplicar estas fuentes.

## Ecosistema Web

### Canal Web  — propietario: `services/comercio_digital/canal_web` (+ `backend/storefront.py`, `gui/canal_web_gui.py`)
- **Objetivo**: ORQUESTADOR del ecosistema web + presencia digital PROPIA (Escenario B).
- **Responsabilidades**: asistente "¿tiene web?"; crear web con **Hostinger**; publicar/regenerar/sincronizar
  la web propia; dominios; marca (`web_config`); pedidos/reservas/pickup/métricas del canal; **redirigir** a
  Marketplace cuando la empresa YA tiene web.
- **NO hace**: integraciones con plataformas externas (Woo/Shopify/…); instalar plugins; TPV; catálogo maestro.
- **Permitidas**: `comercio_digital.*` (conexiones/publicaciones/sync/pickup), `web_tienda`, `secret_manager`,
  `eventbus`, `autorizacion`, `catalogo`(lectura). **Prohibidas**: `marketplace.integraciones_comerciales`
  (solo redirige, no ejecuta), `tpv`, `gui.tpv`.

### Marketplace — propietario: `services/marketplace`
- **Objetivo**: App Store de EXTENSIONES (plugins) + **Integraciones Comerciales** (plataformas ecommerce).
- **Responsabilidades**: (a) plugins: catálogo/repos/firmas/dependencias/licencias/instalación/política; (b)
  integraciones comerciales: conectar/desconectar/validar credenciales/sincronizar productos/pedidos/clientes/
  stock/precios/estados con Woo/Shopify/Prestashop/Amazon/…
- **NO hace**: crear/publicar webs, dominios, Hostinger (eso es Canal Web); vender; gestionar negocio.
- **Propietario del submódulo**: `marketplace/integraciones_comerciales` (reutiliza el catálogo de plataformas
  de `comercio_digital.integraciones_comerciales`). **Prohibidas**: tocar Canal Web/TPV/Catálogo.

### Portal — familia de dominios (aclaración de los 5 homónimos)
- **Portal Web (Back Office)** — `src/portal_web`: versión web para EMPLEADOS; reutiliza services/db/RBAC/
  Entitlements/JWT; multi-tenant por `id_empresa/id_tienda` (nunca dominio). NO es ecommerce ni sustituye TPV.
- **Portal Cliente** — `services/facturacion/portal_cliente`: portal de facturas/documentos para CLIENTES.
- **`services/portal`** (infra Fase V): tipos/scopes de portal (cliente/proveedor/…); **sin frontend ni router**
  → responsabilidad HUÉRFANA (candidata a fusión con `portal_web`, ver CANDIDATOS_FUSION).
- **`gui/portal_empleado`**: portal del empleado de ESCRITORIO (autoconsulta RRHH).
- **`api/routers/portal`**: router delgado que monta `portal_web` en `/api/v1/portal`.

### Catálogo (aclaración de los 6 homónimos — dominios DISTINTOS, NO duplicación)
- `db.catalogo` = **PIM** (datos maestros de producto, overlay sobre `articulos`). Propietario del catálogo.
- `services.catalogo` = **serialización por rol** (vista pública oculta stock; vista interna completa).
- `comercio_digital.catalogo` = **ficha comercial compuesta** (i18n/divisa/IVA, solo lectura para canales).
- `marketplace.catalogo` = **catálogo de PLUGINS** (App Store).
- `seguridad.catalogo` = **catálogo de permisos RBAC**. `autonomia.catalogo` = acciones de autonomía. (ajenos)

## Inventario / Producto

- **Artículos** — `db/articulos`: **FUENTE ÚNICA** de producto/stock/precio. Todo lo demás referencia
  `articulos.codigo`.
- **Stock** — `db/stock`, `services/stock`(adaptador IOC de Smart Stock): consulta/movimientos de existencias
  sobre `articulos`. NO es fuente propia.
- **Inventario** — `services/inventario` (enriquecimiento) + `db/kardex`: kárdex/inventarios físicos.
- **Frontera**: Artículos=maestro; Stock/Inventario=operativa sobre el maestro. (Solape de NOMBRE, no de datos.)

## Producción

- **Producción** — `services/produccion`: gestión de órdenes de fabricación (OF), operativa.
- **MRP** — `services/mrp`: BOM/planificación/costes; integra las OF al kárdex oficial.
- **Frontera**: MRP = planificación/materiales; Producción = ejecución de OF. Evaluar paraguas `fabricacion/`.

## Infraestructura transversal

- **Eventos** — `services/eventos`: **bus interno** de dominio (publicar/suscribir; persiste en `eventos`).
- **EventBus** — `services/eventbus`: **fachada Corporate** sobre `eventos` + hub SSE (`realtime`) +
  distribución multi-instancia. NO es un segundo bus (es la fachada/transporte).
- **Scheduler** — `services/scheduler` (motor de jobs) + `scheduler_enterprise` (schedules con calendario) +
  `scheduler_registry` (catálogo/metadatos de jobs). Un motor, dos capas de gestión.
- **Cloud** — disperso: `platform/cloud` (nodos/cluster prep) · `services/cloud_manager` (SaaS cloud admin) ·
  `services/observabilidad/cloud` (tracing distribuido) · `services/saas_global` (regiones/planes). Consolidar.
- **IA** — `services/ia` (análisis/lectura) · `services/prediccion` (motor predictivo; forecasting único) ·
  `services/inteligencia` (ledger de decisiones supervisadas). Capas, no motores paralelos.
- **Seguridad** — `services/seguridad` (MFA/WebAuthn/secret_manager/tenant_guard) + `services/autorizacion`
  (RBAC) + `saas/entitlements` (capacidades por plan). Tres ejes distintos: identidad/permisos/plan.
- **Storage** — `services/storage` (StorageProvider local/S3) + `storage/documentos` (capa documental).
- **SaaS** — `services/saas` (licensing/planes/enforcement/entitlements/branding/dunning/backup tenant).

## Uso
Este glosario es la **referencia oficial**. Cualquier módulo nuevo debe declararse aquí (ver
GUIA_EVOLUCION_ARQUITECTURA.md) para no reintroducir ambigüedad.
