# INFORME TÉCNICO — FASE WEB-20 · Conector Amazon (primer marketplace)

**Fecha:** 2026-07-31 · **Tipo:** conector de **marketplace** (canal de venta externo) replicando el patrón de
los ecommerce. **Regresiones:** 0 · **Suite:** 792 → **800 passed, 1 skipped** (+8).

## Responsabilidad (marketplace ≠ ecommerce)

Amazon es un **canal externo de venta**: sincroniza productos/pedidos/clientes/stock/precios/estados. **NO**
crea webs, dominios, SSL ni tiendas (sus capacidades en el motor — `_marketplace_tercero` de WEB-13 — ya lo
reflejan: sin `web_creation`/`domain`/`ssl`/`ai_generation`).

## Implementación — `…/integraciones_comerciales/amazon/` (nuevo paquete)

Registrado por el punto de extensión público de WEB-13 (2 líneas aditivas). Nada del núcleo, motor, Centro
(WEB-16.5) ni conectores previos se tocó.

| Módulo | Contenido |
|---|---|
| `adaptador.py` | `AmazonAdapter(motor.adaptadores.AmazonConnector)`: `autenticar` · `validar` · `obtener_version` · `importar_productos/clientes/pedidos` · `exportar_stock/precios` · `actualizar_estado_pedido` · `sincronizacion_inicial/incremental`. Paginación SP-API por `NextToken`; extrae `payload`. Degradable, idempotente, multiempresa. |
| `transporte.py` | `TransporteAmazon` (HTTP real) contra la SP-API (`AMAZON_SPAPI_HOST`) con `x-amz-access-token`. Errores → `motor.errores`. `set_transporte()`. |
| `secretos.py` | Access Token vía `SecretManager` (cifrado). |
| `auditoria.py` | Eventos `AMAZON_AUTH/VALIDATE/IMPORT/EXPORT/SYNC_START/SYNC_FINISH/ERROR`. |

## Reutilización de motores del ERP (N7)

- **Productos**: SP-API Listings → `db.catalogo.upsert_producto(codigo=SKU)` (SKU = `sku`/`sellerSku` o
  `AMAZON-<asin>`) + `actualizar_precio`. Idempotente.
- **Clientes**: Amazon no expone listado de clientes → se **derivan del `BuyerInfo` de los pedidos** (dedup por
  email en `db.clientes`). Nunca duplica.
- **Pedidos**: SP-API Orders + OrderItems → `online_orders_service.crear_pedido_online(plataforma="amazon",
  referencia_externa="AMAZON-<AmazonOrderId>")` — **el MISMO pedido** que TPV/Portal Web/Canal Web/ecommerce.
  Idempotente por referencia externa.
- **Stock/Precios**: `db.stock_almacen` → `PUT listings/2021-08-01/items/{sku}` (patches SP-API).
- **Incremental**: `LastUpdatedAfter` (última sync del motor). No reimporta todo.
- **Estado de pedido**: gestionado por Amazon (Feeds, asíncrono) → preparado, no ejecutado (honesto).

## Cumplido

- **VALIDAR**: host/API/token/permisos/versión/SSL → estado **existente** `VALIDADA`.
- **Centro NO modificado**: Amazon **aparece automáticamente** en el panel. Access Token por SecretManager.
- **Degradable**: `disponible()` solo con Access Token real; sin él → `MISSING_CREDENTIALS`, sin red.
- Reutiliza SecretManager · Auditoría · Estados · Pipeline · Colas · Motores ERP (N7).

## Honestidad

La SP-API de producción exige además **LWA (OAuth)** + firma **AWS SigV4**; esta estructura queda
operativa-ready y degradable (bloqueo externo de credenciales/partner), sin falsear conexiones. Las pruebas
usan un transporte inyectado (costura).

## Pruebas (`test_web20_amazon_real.py`, 8)

Registro + degradable + aparición en el Centro · autenticación + validación · importación productos/clientes
(derivados de BuyerInfo)/pedidos (reutiliza motor: pedido `plataforma=amazon`) · idempotencia/sin duplicados ·
exportación stock/precios · sincronización inicial + incremental · auditoría `AMAZON_*` + multiempresa
(ecommerce intactos) · secretos por SecretManager. **Suite:** 800 passed, 1 skipped (0 regresiones).

## No modificado

Motor WEB-13 · Centro de Integraciones (WEB-16.5) · Hostinger · WooCommerce · Shopify · PrestaShop · Magento ·
OpenCart · Marketplace de Plugins · Canal Web · Portal Web · TPV · Catálogo · Caja · RRHH · AWS · Terraform ·
Docker · Entitlements.

## Siguiente

WEB-21 (eBay) … WEB-24 (TikTok Shop): mismo patrón de marketplace (paquete de 4 ficheros + `registrar()`),
aparición automática en el Centro.
