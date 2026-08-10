# INFORME TÉCNICO — FASE WEB-22 · Conector Miravia (marketplace)

**Fecha:** 2026-07-31 · **Tipo:** conector de **marketplace** replicando el patrón consolidado.
**Regresiones:** 0 · **Suite:** 808 → **816 passed, 1 skipped** (+8).

## Responsabilidad (marketplace)

Miravia es un **canal externo de venta**: sincroniza productos/pedidos/clientes/stock/precios/estados. **NO**
crea webs, dominios, SSL ni tiendas (eso es de Hostinger).

## Implementación — `…/integraciones_comerciales/miravia/` (nuevo paquete)

Registrado por el punto de extensión público de WEB-13 (2 líneas aditivas). Nada del núcleo, motor, Centro
(WEB-16.5) ni conectores previos se tocó.

| Módulo | Contenido |
|---|---|
| `adaptador.py` | `MiraviaAdapter(motor.adaptadores.MiraviaConnector)`: `autenticar` · `validar` · `obtener_version` · `importar_productos/clientes/pedidos` · `exportar_stock/precios` · `actualizar_estado_pedido` · `sincronizacion_inicial/incremental` (exactamente esos, sin métodos extra). Paginación `limit/offset`; extrae `{key}`/`data`/`result`. Degradable, idempotente, multiempresa. |
| `transporte.py` | `TransporteMiravia` (HTTP real) contra la API abierta de Miravia con Access Token (`Bearer` + `X-Miravia-Access-Token`). Errores → `motor.errores`. `set_transporte()`. |
| `secretos.py` | Access Token vía `SecretManager` (cifrado). |
| `auditoria.py` | Eventos `MIRAVIA_AUTH/VALIDATE/IMPORT/EXPORT/SYNC_START/SYNC_FINISH/ERROR`. |

## Reutilización de motores del ERP (N7)

- **Productos**: `db.catalogo.upsert_producto(codigo=SKU)` (SKU = `sku`/`seller_sku` o `MIRAVIA-<item_id>`) +
  `actualizar_precio`. Idempotente.
- **Clientes**: Miravia solo da clientes asociados a pedidos → se **derivan del comprador de los pedidos**
  (dedup por email en `db.clientes`). Nunca listado independiente. Nunca duplica.
- **Pedidos**: `online_orders_service.crear_pedido_online(plataforma="miravia", referencia_externa="MIRAVIA-<id>")`
  — **el MISMO pedido** que WooCommerce/Shopify/Amazon/eBay. NO crea `PedidoMiravia`/`PedidoMarketplace`/
  `PedidoWeb`. Idempotente por referencia externa.
- **Stock/Precios**: `db.stock_almacen` → `PUT products/{id}`.
- **Incremental**: filtro `update_after` (última sync del motor). No reimporta todo el catálogo.

## Cumplido / honestidad

- **VALIDAR**: host/API/token/permisos/versión/SSL → estado **existente** `VALIDADA`.
- **Centro NO modificado**: Miravia **aparece automáticamente** (sistema de registro de adaptadores).
- **Degradable**: `disponible()` solo con Access Token real; sin él → `MISSING_CREDENTIALS`, sin red.
- La API de Miravia (plataforma abierta tipo Alibaba/TOP) usa app_key/app_secret + firma/sesión → bloqueo
  externo, estructura operativa-ready y degradable, sin falsear conexiones. Reutiliza SecretManager · Auditoría
  · Estados · Pipeline · Colas · Motores ERP (N7).

## Pruebas (`test_web22_miravia_real.py`, 8)

Registro + degradable + aparición en el Centro · autenticación + validación · importación productos/clientes
(derivados de pedidos)/pedidos (reutiliza motor: pedido `plataforma=miravia`) · idempotencia/sin duplicados ·
exportación stock/precios · sincronización inicial + incremental · auditoría `MIRAVIA_*` + multiempresa
(Amazon/eBay/ecommerce intactos) · secretos por SecretManager. **Suite:** 816 passed, 1 skipped (0 regresiones).

## No modificado

Motor WEB-13 · Centro (WEB-16.5) · Hostinger · WooCommerce · Shopify · PrestaShop · Magento · OpenCart · Amazon ·
eBay · Marketplace de Plugins · Canal Web · Portal Web · TPV · Catálogo · Caja · Facturación · RRHH · AWS ·
Terraform · Docker · RBAC · Entitlements · Licencias SaaS.

## Siguiente

WEB-23 (AliExpress) · WEB-24 (TikTok Shop): mismo patrón de marketplace.
