# INFORME TÉCNICO — FASE WEB-16 · Conector Shopify (segunda integración comercial)

**Fecha:** 2026-07-31 · **Tipo:** segundo conector comercial real, EXCLUSIVAMENTE en `shopify/` (mismo patrón
que WooCommerce; motor WEB-13, Hostinger y WooCommerce intactos). **Regresiones:** 0 · **Suite:** 754 →
**762 passed, 1 skipped** (+8).

## Objetivo

Integración completa con Shopify reutilizando la arquitectura del motor de Integraciones Comerciales y el
mismo patrón que WooCommerce, sin modificar el núcleo.

## Implementación — `…/integraciones_comerciales/shopify/` (nuevo paquete)

Registrado en el motor por el punto de extensión público de WEB-13 (`registrar_adaptador`) desde la fachada.
`motor/`, Hostinger, WooCommerce y Marketplace de Plugins **no se tocan**.

| Módulo | Contenido |
|---|---|
| `adaptador.py` | `ShopifyAdapter(motor.adaptadores.ShopifyConnector)`: `autenticar` · `validar` · `obtener_version` · `importar_productos/clientes/pedidos` · `exportar_stock/precios` · `actualizar_estado_pedido` · `sincronizacion_inicial/incremental`. Paginación genérica por `since_id`. Degradable, idempotente, multiempresa. |
| `transporte.py` | `TransporteShopify` (HTTP real, `requests`) contra la Shopify Admin REST API `/admin/api/{version}/` con cabecera `X-Shopify-Access-Token`. Errores → `motor.errores`. `set_transporte()` (costura). |
| `secretos.py` | Access Token vía `SecretManager` (cifrado Fernet; runtime cifrado por referencia; producción entorno/AWS). Shop URL no es secreto (va en la integración). |
| `auditoria.py` | Eventos `SHOPIFY_AUTH/VALIDATE/IMPORT/EXPORT/SYNC_START/SYNC_FINISH/ERROR`. |

## Reutilización de motores del ERP (N7, idéntico a WooCommerce)

- **Productos**: `db.catalogo.upsert_producto(codigo=SKU)` idempotente + `db.articulos.actualizar_precio`.
  SKU desde `variants[0].sku`; si no, `SHOPIFY-<id>`. Nunca duplica.
- **Clientes**: `db.clientes` — clave **email** (dedup por `buscar_clientes`). Nunca duplica.
- **Pedidos**: `online_orders_service.crear_pedido_online(plataforma="shopify", referencia_externa="SHOPIFY-<id>")`
  — **el MISMO pedido** que TPV/Portal Web/Canal Web/WooCommerce. NO se crea `PedidoShopify`/`PedidoWeb`/
  `PedidoMarketplace`. Idempotente por referencia externa.
- **Stock/Precios**: `db.stock_almacen` (solo de la empresa) → `PUT products/{id}.json` (variants).

## Autenticación / validación / secretos

- **Autenticación**: Shopify Admin API con **Shop URL + Access Token** (nunca en claro; SecretManager).
- **VALIDAR**: URL, acceso API, token, permisos, versión de API, SSL. Actualiza SOLO el **estado existente**
  (→ `VALIDADA`); no crea estados nuevos.

## Sincronización

- **Inicial**: importación completa (productos/clientes/pedidos), idempotente, sin borrar datos.
- **Incremental**: usa la **última sincronización** del motor (`servicio…ultima_sync`) con `updated_at_min`;
  nunca reimporta todo. Reutiliza estados/`servicio.sincronizar`.

## Interfaz (mismo diseño que WooCommerce)

Asistente existente (flujo NO modificado) + campo **Access Token** (Shop URL = campo URL). Cifrado vía
SecretManager. Botones **Validar/Sincronizar** del centro enrutan al **adaptador operativo** (dirigido por
adaptador — `disponible()`+`hasattr`, no `if plataforma==`). Sin pasos adicionales.

## Restricciones respetadas

Sin webhooks/OAuth completo/sincronización automática/polling/jobs/colas remotas: preparado con las **costuras
existentes** del motor (transporte inyectable, colas del motor, estados) pero **no activado**. Honestidad
degradable: `disponible()` solo con Shop URL + Access Token reales; sin ellos → `MISSING_CREDENTIALS`, sin red.

## Plantilla para el resto de plataformas

El patrón (adaptador + transporte inyectable + SecretManager + reutilización de motores ERP + estados/pipeline
del motor + paginación genérica) es idéntico a WooCommerce → PrestaShop/Magento/OpenCart/Amazon/eBay/Miravia/
AliExpress/TikTok se implementan replicándolo, cada uno en su fase, sin tocar el núcleo.

## Corrección de regresión latente (WEB-08)

Al ejercitarse el panel operativo de `PortalWebHome` (extraído del TPV en WEB-08) con datos reales de pedidos
—generados por los tests de conectores— afloró un `NameError: divisas` (import no trasladado en la extracción
WEB-08). **Corregido** añadiendo `from src.utils import divisas` a `gui/portal_web_home.py`. Suite verde.

## Pruebas (`test_web16_shopify_real.py`, 8)

Registro + degradable · autenticación + validación · importación productos/clientes/pedidos (reutiliza motor:
pedido `plataforma=shopify`, mismo `online_orders`) · idempotencia/sin duplicados · exportación stock/precios ·
sincronización inicial + incremental · auditoría `SHOPIFY_*` + multiempresa (WooCommerce intacto) · secretos
por SecretManager (Access Token cifrado). **Suite:** 762 passed, 1 skipped (0 regresiones sobre 754).

## No modificado (§11)

WooCommerce · Hostinger · Canal Web · Portal Web · TPV · Marketplace de Plugins · Catálogo · Caja · RRHH ·
AWS · Terraform · Docker · Entitlements · **motor WEB-13**: intactos. Los motores ERP se REUTILIZAN.
