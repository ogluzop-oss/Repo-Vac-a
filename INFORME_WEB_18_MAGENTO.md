# INFORME TÉCNICO — FASE WEB-18 · Conector Magento

**Fecha:** 2026-07-31 · **Tipo:** conector comercial real replicando el patrón WooCommerce/Shopify/PrestaShop.
**Regresiones:** 0 · **Suite:** 776 → **784 passed, 1 skipped** (+8).

## Implementación — `…/integraciones_comerciales/magento/` (nuevo paquete)

Registrado en el motor por el punto de extensión público de WEB-13 (2 líneas aditivas en la fachada). Nada del
núcleo, motor, Centro (WEB-16.5) ni conectores previos se tocó.

| Módulo | Contenido |
|---|---|
| `adaptador.py` | `MagentoAdapter(motor.adaptadores.MagentoConnector)`: `autenticar` · `validar` · `obtener_version` · `importar_productos/clientes/pedidos` · `exportar_stock/precios` · `actualizar_estado_pedido` · `sincronizacion_inicial/incremental`. Paginación `searchCriteria[pageSize]/[currentPage]`. Degradable, idempotente, multiempresa. |
| `transporte.py` | `TransporteMagento` (HTTP real, `requests`) contra Magento 2 REST `/rest/V1/…` con `Authorization: Bearer {token}`. Errores → `motor.errores`. `set_transporte()`. |
| `secretos.py` | Access Token vía `SecretManager` (cifrado). |
| `auditoria.py` | Eventos `MAGENTO_AUTH/VALIDATE/IMPORT/EXPORT/SYNC_START/SYNC_FINISH/ERROR`. |

## Reutilización de motores del ERP (N7, idéntica al patrón)

- **Productos**: `db.catalogo.upsert_producto(codigo=SKU)` (SKU = `sku` o `MAGENTO-<id>`) + `actualizar_precio`.
  Idempotente.
- **Clientes**: `db.clientes`, clave **email** (`customers/search`). Nunca duplica.
- **Pedidos**: `online_orders_service.crear_pedido_online(plataforma="magento", referencia_externa="MAGENTO-<entity_id>")`
  — **el MISMO pedido** que TPV/Portal Web/Canal Web/Woo/Shopify/PrestaShop (líneas de `order.items`). Idempotente.
- **Stock/Precios**: `db.stock_almacen` (solo de la empresa) → `PUT products/{sku}` (extension_attributes.stock_item / price).
- **Incremental**: `searchCriteria` filtro `updated_at gteq` (última sync del motor). No reimporta todo.

## Cumplido

- **VALIDAR**: URL/API/token/permisos/versión/SSL → estado **existente** `VALIDADA`.
- **Centro NO modificado**: Magento **aparece automáticamente** en el panel (unión catálogo + adaptadores).
  Access Token por SecretManager (`MAGENTO_ACCESS_TOKEN` o `{ref}_ACCESS_TOKEN`).
- **Degradable**: `disponible()` solo con URL + Access Token reales; sin ellos → `MISSING_CREDENTIALS`, sin red.
- Reutiliza SecretManager · Auditoría · Estados · Pipeline · Colas · Motores ERP (N7).

## Pruebas (`test_web18_magento_real.py`, 8)

Registro + degradable + aparición en el Centro · autenticación + validación · importación productos/clientes/
pedidos (reutiliza motor: pedido `plataforma=magento`) · idempotencia/sin duplicados · exportación stock/precios ·
sincronización inicial + incremental · auditoría `MAGENTO_*` + multiempresa (Woo/Shopify/Presta intactos) ·
secretos por SecretManager. **Suite:** 784 passed, 1 skipped (0 regresiones).

## No modificado

Motor WEB-13 · Centro de Integraciones (WEB-16.5) · Hostinger · WooCommerce · Shopify · PrestaShop · Marketplace
de Plugins · Canal Web · Portal Web · TPV · Catálogo · Caja · RRHH · AWS · Terraform · Docker · Entitlements.

## Siguiente

WEB-19 (OpenCart) … WEB-24 (TikTok Shop): mismo patrón (paquete de 4 ficheros + `registrar()`), aparición
automática en el Centro.
