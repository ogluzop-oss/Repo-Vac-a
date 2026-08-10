# INFORME TÉCNICO — FASE WEB-21 · Conector eBay (marketplace)

**Fecha:** 2026-07-31 · **Tipo:** conector de **marketplace** replicando el patrón consolidado.
**Regresiones:** 0 · **Suite:** 800 → **808 passed, 1 skipped** (+8).

## Responsabilidad (marketplace)

eBay es un **canal externo de venta**: sincroniza productos/pedidos/clientes/stock/precios/estados. **NO**
crea webs, dominios, SSL ni tiendas.

## Implementación — `…/integraciones_comerciales/ebay/` (nuevo paquete)

Registrado por el punto de extensión público de WEB-13 (2 líneas aditivas). Nada del núcleo, motor, Centro
(WEB-16.5) ni conectores previos se tocó.

| Módulo | Contenido |
|---|---|
| `adaptador.py` | `EbayAdapter(motor.adaptadores.EbayConnector)`: `autenticar` · `validar` · `obtener_version` · `importar_productos/clientes/pedidos` · `exportar_stock/precios` · `actualizar_estado_pedido` · `sincronizacion_inicial/incremental`. Paginación `limit/offset`. Degradable, idempotente, multiempresa. |
| `transporte.py` | `TransporteEbay` (HTTP real) contra las eBay Sell APIs (`/sell/{api}/v1/…`) con OAuth2 `Authorization: Bearer`. Errores → `motor.errores`. `set_transporte()`. |
| `secretos.py` | Access Token (OAuth2) vía `SecretManager` (cifrado). |
| `auditoria.py` | Eventos `EBAY_AUTH/VALIDATE/IMPORT/EXPORT/SYNC_START/SYNC_FINISH/ERROR`. |

## Reutilización de motores del ERP (N7)

- **Productos**: Inventory API → `db.catalogo.upsert_producto(codigo=SKU)` (SKU = `sku` o `EBAY-<epid>`) +
  `actualizar_precio`. Idempotente.
- **Clientes**: eBay no expone listado → se **derivan del `buyer` de los pedidos** (dedup por email/username en
  `db.clientes`). Nunca duplica.
- **Pedidos**: Fulfillment Order API → `online_orders_service.crear_pedido_online(plataforma="ebay",
  referencia_externa="EBAY-<orderId>")` — **el MISMO pedido** que TPV/Portal Web/Canal Web/ecommerce/Amazon.
  Idempotente por referencia externa.
- **Stock**: `PUT sell/inventory/v1/inventory_item/{sku}` (availability). **Precios**: `PUT .../offer/{sku}`
  (la Offer de eBay; preparado por SKU).
- **Incremental**: filtro `lastmodifieddate` (última sync del motor). No reimporta todo.
- **Estado de pedido**: shipping fulfillment (preparado).

## Cumplido / honestidad

- **VALIDAR**: host/API/token/permisos/versión/SSL → estado **existente** `VALIDADA`.
- **Centro NO modificado**: eBay **aparece automáticamente**. Access Token por SecretManager.
- **Degradable**: `disponible()` solo con Access Token real; sin él → `MISSING_CREDENTIALS`, sin red.
- Las eBay Sell APIs usan **OAuth2** (token de usuario + scopes) → bloqueo externo, estructura
  operativa-ready y degradable, sin falsear conexiones. Reutiliza SecretManager · Auditoría · Estados ·
  Pipeline · Colas · Motores ERP (N7).

## Pruebas (`test_web21_ebay_real.py`, 8)

Registro + degradable + aparición en el Centro · autenticación + validación · importación productos/clientes
(derivados del buyer)/pedidos (reutiliza motor: pedido `plataforma=ebay`) · idempotencia/sin duplicados ·
exportación stock/precios · sincronización inicial + incremental · auditoría `EBAY_*` + multiempresa
(Amazon/ecommerce intactos) · secretos por SecretManager. **Suite:** 808 passed, 1 skipped (0 regresiones).

## No modificado

Motor WEB-13 · Centro (WEB-16.5) · Hostinger · WooCommerce · Shopify · PrestaShop · Magento · OpenCart · Amazon ·
Marketplace de Plugins · Canal Web · Portal Web · TPV · Catálogo · Caja · RRHH · AWS · Terraform · Docker ·
Entitlements.

## Siguiente

WEB-22 (Miravia) · WEB-23 (AliExpress) · WEB-24 (TikTok Shop): mismo patrón de marketplace.
