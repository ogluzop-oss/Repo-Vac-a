# INFORME TÉCNICO — FASE WEB-24 · Conector TikTok Shop (cierre del ecosistema)

**Fecha:** 2026-07-31 · **Tipo:** último conector de **marketplace**; completa el ecosistema de Integraciones
Comerciales. **Regresiones:** 0 · **Suite:** 824 → **832 passed, 1 skipped** (+8).

## Implementación — `…/integraciones_comerciales/tiktok_shop/` (nuevo paquete)

Registrado por el punto de extensión público de WEB-13 (2 líneas aditivas). Nada del núcleo, motor, Centro
(WEB-16.5) ni conectores previos se tocó.

| Módulo | Contenido |
|---|---|
| `adaptador.py` | `TikTokShopAdapter(motor.adaptadores.TikTokShopConnector)`: los 11 métodos requeridos (sin extras). Paginación `page_size/page_number`; extrae `{key}`/`data`. Degradable, idempotente, multiempresa. |
| `transporte.py` | `TransporteTikTokShop` (HTTP real) contra la TikTok Shop Partner API con Access Token (`Bearer` + `x-tts-access-token`). Errores → `motor.errores`. `set_transporte()`. |
| `secretos.py` | Access Token vía `SecretManager` (cifrado). |
| `auditoria.py` | Eventos `TIKTOK_AUTH/VALIDATE/IMPORT/EXPORT/SYNC_START/SYNC_FINISH/ERROR`. |

## Reutilización de motores del ERP (N7)

- **Productos**: `db.catalogo.upsert_producto(codigo=SKU)` (SKU = `skus[0].seller_sku`/`sku` o `TIKTOK-<id>`) +
  `actualizar_precio`. Idempotente.
- **Clientes**: solo asociados a pedidos → se **derivan del comprador de los pedidos** (dedup por email en
  `db.clientes`). Nunca listado independiente. Nunca duplica.
- **Pedidos**: `online_orders_service.crear_pedido_online(plataforma="tiktok_shop", referencia_externa="TIKTOK-<id>")`
  — **el MISMO pedido** que todo el resto. NO crea `PedidoTikTok`/`PedidoMarketplace`/`PedidoWeb`. Idempotente.
- **Stock/Precios**: `db.stock_almacen` → `PUT product/202309/products/{id}/inventory|prices/update`.
- **Incremental**: filtro `update_time_ge` (última sync del motor). No reimporta todo el catálogo.

## Cumplido / honestidad

- **VALIDAR**: host/API/token/permisos/versión/SSL → estado **existente** `VALIDADA`.
- **Centro NO modificado**: TikTok Shop **aparece automáticamente** (registro de adaptadores).
- **Degradable**: `disponible()` solo con Access Token real; sin él → `MISSING_CREDENTIALS`, sin red.
- La TikTok Shop Partner API usa app_key/app_secret + access_token (shop) + firma → bloqueo externo,
  estructura operativa-ready y degradable, sin falsear conexiones. Reutiliza SecretManager · Auditoría ·
  Estados · Pipeline · Colas · Motores ERP (N7).

## Pruebas (`test_web24_tiktok_shop_real.py`, 8)

Registro + degradable + aparición en el Centro · autenticación + validación · importación productos/clientes
(derivados de pedidos)/pedidos (reutiliza motor: pedido `plataforma=tiktok_shop`) · idempotencia/sin
duplicados · exportación stock/precios · sincronización inicial + incremental · auditoría `TIKTOK_*` +
multiempresa (todo el ecosistema presente) · secretos por SecretManager. **Suite:** 832 passed, 1 skipped
(0 regresiones).

## ✅ Ecosistema de Integraciones Comerciales COMPLETO (11 conectores reales)

Verificado en el Centro (`plataformas_soportadas` → 11 adaptadores reales, 0 placeholders):

- **Creación web con IA**: Hostinger (WEB-14)
- **eCommerce (tienda propia)**: WooCommerce (WEB-15) · Shopify (WEB-16) · PrestaShop (WEB-17) · Magento
  (WEB-18) · OpenCart (WEB-19)
- **Marketplaces (canal externo)**: Amazon (WEB-20) · eBay (WEB-21) · Miravia (WEB-22) · AliExpress (WEB-23) ·
  TikTok Shop (WEB-24)

Todos comparten: motor WEB-13 (capacidades/pipeline/estados/errores/colas), Centro WEB-16.5 (panel escalable,
health, estadísticas, historial, cola local), SecretManager, auditoría (`log_auditoria`), y los MISMOS motores
ERP (catálogo/clientes/**pedidos vía `online_orders_service`**/stock). Degradables y honestos: operativos solo
con credenciales reales (bloqueos externos documentados por plataforma).

## No modificado

Motor WEB-13 · Centro (WEB-16.5) · todos los conectores previos · Marketplace de Plugins · Portal Cliente ·
Canal Web · Portal Web · TPV · Catálogo · Caja · Facturación · RRHH · Producción · AWS · Terraform · Docker ·
RBAC · Entitlements · Licencias SaaS.
