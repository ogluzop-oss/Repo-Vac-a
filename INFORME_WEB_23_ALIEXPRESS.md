# INFORME TÉCNICO — FASE WEB-23 · Conector AliExpress (marketplace)

**Fecha:** 2026-07-31 · **Tipo:** conector de **marketplace** replicando el patrón consolidado.
**Regresiones:** 0 · **Suite:** 816 → **824 passed, 1 skipped** (+8).

## Responsabilidad (marketplace)

AliExpress es un **canal externo de venta**: sincroniza productos/pedidos/clientes/stock/precios/estados.
**NO** crea webs, dominios, SSL ni tiendas (eso es de Hostinger).

## Implementación — `…/integraciones_comerciales/aliexpress/` (nuevo paquete)

Registrado por el punto de extensión público de WEB-13 (2 líneas aditivas). Nada del núcleo, motor, Centro
(WEB-16.5) ni conectores previos se tocó.

| Módulo | Contenido |
|---|---|
| `adaptador.py` | `AliExpressAdapter(motor.adaptadores.AliExpressConnector)`: los 11 métodos requeridos (sin extras). Paginación `limit/offset`; extrae `{key}`/`data`/`result`. Degradable, idempotente, multiempresa. |
| `transporte.py` | `TransporteAliExpress` (HTTP real) contra la Alibaba Open Platform con Access Token (`Bearer` + `X-Aliexpress-Access-Token`). Errores → `motor.errores`. `set_transporte()`. |
| `secretos.py` | Access Token vía `SecretManager` (cifrado). |
| `auditoria.py` | Eventos `ALIEXPRESS_AUTH/VALIDATE/IMPORT/EXPORT/SYNC_START/SYNC_FINISH/ERROR`. |

## Reutilización de motores del ERP (N7)

- **Productos**: `db.catalogo.upsert_producto(codigo=SKU)` (SKU = `sku`/`seller_sku` o `ALIEXPRESS-<product_id>`)
  + `actualizar_precio`. Idempotente.
- **Clientes**: AliExpress solo expone clientes asociados a pedidos → se **derivan del comprador de los
  pedidos** (dedup por email en `db.clientes`). Nunca listado independiente. Nunca duplica.
- **Pedidos**: `online_orders_service.crear_pedido_online(plataforma="aliexpress", referencia_externa="ALIEXPRESS-<id>")`
  — **el MISMO pedido** que WooCommerce/Shopify/Amazon/eBay/Miravia. NO crea `PedidoAliExpress`/
  `PedidoMarketplace`/`PedidoWeb`. Idempotente por referencia externa.
- **Stock/Precios**: `db.stock_almacen` → `PUT products/{id}`.
- **Incremental**: filtro `update_after` (última sync del motor). No reimporta todo el catálogo.

## Cumplido / honestidad

- **VALIDAR**: host/API/token/permisos/versión/SSL → estado **existente** `VALIDADA`.
- **Centro NO modificado**: AliExpress **aparece automáticamente** (sistema de registro de adaptadores).
- **Degradable**: `disponible()` solo con Access Token real; sin él → `MISSING_CREDENTIALS`, sin red.
- La Alibaba Open Platform (TOP) usa app_key/app_secret + firma/sesión → bloqueo externo, estructura
  operativa-ready y degradable, sin falsear conexiones. Reutiliza SecretManager · Auditoría · Estados ·
  Pipeline · Colas · Motores ERP (N7).

## Pruebas (`test_web23_aliexpress_real.py`, 8)

Registro + degradable + aparición en el Centro · autenticación + validación · importación productos/clientes
(derivados de pedidos)/pedidos (reutiliza motor: pedido `plataforma=aliexpress`) · idempotencia/sin duplicados
· exportación stock/precios · sincronización inicial + incremental · auditoría `ALIEXPRESS_*` + multiempresa
(Amazon/eBay/Miravia/ecommerce intactos) · secretos por SecretManager. **Suite:** 824 passed, 1 skipped
(0 regresiones).

## No modificado

Motor WEB-13 · Centro (WEB-16.5) · Hostinger · WooCommerce · Shopify · PrestaShop · Magento · OpenCart · Amazon ·
eBay · Miravia · Marketplace de Plugins · Portal Cliente · Canal Web · Portal Web · TPV · Catálogo · Caja ·
Facturación · RRHH · AWS · Terraform · Docker · RBAC · Entitlements · Licencias SaaS.

## Siguiente

WEB-24 (TikTok Shop): último marketplace, mismo patrón.
