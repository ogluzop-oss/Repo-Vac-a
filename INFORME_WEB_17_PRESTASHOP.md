# INFORME TÉCNICO — FASE WEB-17 · Conector PrestaShop

**Fecha:** 2026-07-31 · **Tipo:** conector comercial real replicando EXACTAMENTE el patrón WooCommerce/Shopify.
**Regresiones:** 0 · **Suite:** 768 → **776 passed, 1 skipped** (+8).

## Objetivo

Implementar el conector de PrestaShop sin modificar el núcleo, el motor WEB-13, el Centro de Integraciones
(WEB-16.5) ni los conectores existentes (Hostinger/WooCommerce/Shopify).

## Implementación — `…/integraciones_comerciales/prestashop/` (nuevo paquete)

Registrado en el motor por el punto de extensión público de WEB-13 (`registrar_adaptador`) desde la fachada
(2 líneas aditivas). Nada del núcleo, motor, Centro ni conectores previos se tocó.

| Módulo | Contenido |
|---|---|
| `adaptador.py` | `PrestaShopAdapter(motor.adaptadores.PrestaShopConnector)`: `autenticar` · `validar` · `obtener_version` · `importar_productos/clientes/pedidos` · `exportar_stock/precios` · `actualizar_estado_pedido` · `sincronizacion_inicial/incremental`. Paginación `limit=offset,count`. Degradable, idempotente, multiempresa. |
| `transporte.py` | `TransportePresta` (HTTP real, `requests`) contra el PrestaShop Webservice `/api/{recurso}` con API Key (Basic key:'') + `output_format=JSON`. Errores → `motor.errores`. `set_transporte()`. |
| `secretos.py` | API Key vía `SecretManager` (cifrado; runtime cifrado por referencia; producción entorno/AWS). |
| `auditoria.py` | Eventos `PRESTA_AUTH/VALIDATE/IMPORT/EXPORT/SYNC_START/SYNC_FINISH/ERROR`. |

## Reutilización de motores del ERP (N7, idéntica al patrón)

- **Productos**: `db.catalogo.upsert_producto(codigo=SKU)` (SKU = `reference` o `PRESTA-<id>`) + `actualizar_precio`.
  Campos traducibles (`name` str|lista) normalizados. Nunca duplica.
- **Clientes**: `db.clientes`, clave **email** (dedup). Nunca duplica.
- **Pedidos**: `online_orders_service.crear_pedido_online(plataforma="prestashop", referencia_externa="PRESTA-<id>")`
  — **el MISMO pedido** que TPV/Portal Web/Canal Web/WooCommerce/Shopify. Líneas desde `associations.order_rows`.
  Idempotente por referencia externa.
- **Stock/Precios**: `db.stock_almacen` (solo de la empresa) → `PUT stock_availables/{id}` / `PUT products/{id}`.

## Validación / secretos / interfaz

- **VALIDAR**: URL, acceso API, API Key, permisos, versión (`configurations` PS_VERSION_DB), SSL → estado
  **existente** `VALIDADA`.
- **Incremental**: usa la última sincronización del motor (`filter[date_upd]`); no reimporta todo.
- **Interfaz**: **el Centro NO se modificó** (congelado en WEB-16.5). PrestaShop **aparece automáticamente** en
  el panel (unión catálogo + adaptadores). La API Key se provisiona por SecretManager (`PRESTASHOP_API_KEY` o
  `{ref}_API_KEY`); la Shop URL se captura con el campo URL del asistente existente.
- **Honestidad**: `disponible()` solo con Shop URL + API Key reales; sin ellas → `MISSING_CREDENTIALS`, sin red.

## Pruebas (`test_web17_prestashop_real.py`, 8)

Registro + degradable + aparición en el Centro · autenticación + validación (versión/SSL) · importación
productos/clientes/pedidos (reutiliza motor: pedido `plataforma=prestashop`) · idempotencia/sin duplicados ·
exportación stock/precios · sincronización inicial + incremental · auditoría `PRESTA_*` + multiempresa
(WooCommerce/Shopify intactos) · secretos por SecretManager. **Suite:** 776 passed, 1 skipped (0 regresiones).

## No modificado

Motor WEB-13 · Centro de Integraciones (WEB-16.5) · Hostinger · WooCommerce · Shopify · Marketplace de Plugins ·
Canal Web · Portal Web · TPV · Catálogo · Caja · RRHH · AWS · Terraform · Docker · Entitlements: intactos.

## Siguiente

WEB-18 (Magento) … WEB-24 (TikTok Shop): mismo patrón (paquete de 4 ficheros + `registrar()`), aparición
automática en el Centro, sin tocar el núcleo.
