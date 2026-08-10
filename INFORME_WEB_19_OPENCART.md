# INFORME TÉCNICO — FASE WEB-19 · Conector OpenCart

**Fecha:** 2026-07-31 · **Tipo:** conector comercial real replicando el patrón WooCommerce/Shopify/PrestaShop/
Magento. **Regresiones:** 0 · **Suite:** 784 → **792 passed, 1 skipped** (+8).

## Implementación — `…/integraciones_comerciales/opencart/` (nuevo paquete)

Registrado por el punto de extensión público de WEB-13 (2 líneas aditivas en la fachada). Nada del núcleo,
motor, Centro (WEB-16.5) ni conectores previos se tocó.

| Módulo | Contenido |
|---|---|
| `adaptador.py` | `OpenCartAdapter(motor.adaptadores.OpenCartConnector)`: `autenticar` · `validar` · `obtener_version` · `importar_productos/clientes/pedidos` · `exportar_stock/precios` · `actualizar_estado_pedido` · `sincronizacion_inicial/incremental`. Paginación `page/limit`; extrae `{recurso}`/`data`. Degradable, idempotente, multiempresa. |
| `transporte.py` | `TransporteOpenCart` (HTTP real) contra el OpenCart REST API (prefijo configurable `OPENCART_REST_PREFIX`, def. `api/rest`) con API Key `X-Oc-Api-Key`. Errores → `motor.errores`. `set_transporte()`. |
| `secretos.py` | API Key vía `SecretManager` (cifrada). |
| `auditoria.py` | Eventos `OPENCART_AUTH/VALIDATE/IMPORT/EXPORT/SYNC_START/SYNC_FINISH/ERROR`. |

## Reutilización de motores del ERP (N7, idéntica al patrón)

- **Productos**: `db.catalogo.upsert_producto(codigo=SKU)` (SKU = `sku`/`model` o `OPENCART-<product_id>`) +
  `actualizar_precio`. Idempotente.
- **Clientes**: `db.clientes`, clave **email**. Nunca duplica.
- **Pedidos**: `online_orders_service.crear_pedido_online(plataforma="opencart", referencia_externa="OPENCART-<order_id>")`
  — **el MISMO pedido** que TPV/Portal Web/Canal Web/Woo/Shopify/Presta/Magento (líneas de `order.products`).
  Idempotente por referencia externa.
- **Stock/Precios**: `db.stock_almacen` (solo de la empresa) → `PUT products/{product_id}` (quantity/price).
- **Incremental**: filtro `filter_date_modified` (última sync del motor). No reimporta todo.

## Cumplido

- **VALIDAR**: URL/API/API Key/permisos/versión/SSL → estado **existente** `VALIDADA`.
- **Centro NO modificado**: OpenCart **aparece automáticamente** en el panel (unión catálogo + adaptadores).
  API Key por SecretManager (`OPENCART_API_KEY` o `{ref}_API_KEY`).
- **Degradable**: `disponible()` solo con URL + API Key reales; sin ellas → `MISSING_CREDENTIALS`, sin red.
- Reutiliza SecretManager · Auditoría · Estados · Pipeline · Colas · Motores ERP (N7).

## Pruebas (`test_web19_opencart_real.py`, 8)

Registro + degradable + aparición en el Centro · autenticación + validación · importación productos/clientes/
pedidos (reutiliza motor: pedido `plataforma=opencart`) · idempotencia/sin duplicados · exportación stock/
precios · sincronización inicial + incremental · auditoría `OPENCART_*` + multiempresa (Woo/Shopify/Presta/
Magento intactos) · secretos por SecretManager. **Suite:** 792 passed, 1 skipped (0 regresiones).

## No modificado

Motor WEB-13 · Centro de Integraciones (WEB-16.5) · Hostinger · WooCommerce · Shopify · PrestaShop · Magento ·
Marketplace de Plugins · Canal Web · Portal Web · TPV · Catálogo · Caja · RRHH · AWS · Terraform · Docker ·
Entitlements.

## Siguiente

WEB-20 (Amazon) … WEB-24 (TikTok Shop): mismo patrón (paquete de 4 ficheros + `registrar()`), aparición
automática en el Centro. (Los marketplaces Amazon/eBay/… no gestionan creación web ni dominio; solo
productos/pedidos/clientes/stock/precios, ya reflejado en sus capacidades del motor.)
