# INFORME TÉCNICO — FASE WEB-15 · Conector WooCommerce (primer conector comercial)

**Fecha:** 2026-07-31 · **Tipo:** primer conector comercial real, EXCLUSIVAMENTE en el conector WooCommerce
(motor WEB-13 intacto; patrón WEB-14). **Regresiones:** 0 · **Suite:** 746 → **754 passed, 1 skipped** (+8).

## Objetivo

Conectar una tienda WooCommerce existente con el Marketplace vía el motor de Integraciones Comerciales,
reutilizando toda la arquitectura y los motores del ERP, sin modificar el núcleo.

## Implementación — `…/integraciones_comerciales/woocommerce/` (nuevo paquete)

Registrado en el motor por el punto de extensión público de WEB-13 (`registrar_adaptador`), desde la fachada.
`motor/`, Hostinger y el resto **no se tocan**.

| Módulo | Contenido |
|---|---|
| `adaptador.py` | `WooCommerceAdapter(motor.adaptadores.WooCommerceConnector)`: `autenticar` · `validar` · `obtener_version` · `importar_productos/clientes/pedidos` · `exportar_stock/precios` · `actualizar_estado_pedido` · `sincronizacion_inicial/incremental`. Degradable, idempotente, multiempresa. |
| `transporte.py` | `TransporteWoo` (HTTP real, `requests`) contra la WooCommerce REST API `/wp-json/wc/v3/` con auth Consumer Key/Secret (Basic sobre HTTPS). Errores → `motor.errores`. `set_transporte()` (costura). |
| `secretos.py` | Consumer Key/Secret vía `SecretManager` (cifrado Fernet; runtime cifrado en memoria por referencia; producción vía entorno/AWS). Nunca en claro. |
| `auditoria.py` | Eventos `WOO_AUTH/VALIDATE/IMPORT/EXPORT/SYNC_START/SYNC_FINISH/ERROR`. |

## Reutilización de motores del ERP (N7 — NO se duplica lógica)

- **Productos**: `db.catalogo.upsert_producto(codigo=SKU)` (idempotente por SKU) + `db.articulos.actualizar_precio`.
  Relación por **SKU** si existe; si no, identificador Smart Manager `WOO-<id>`. Nunca duplica artículos.
- **Clientes**: `db.clientes` — dedup por email (`buscar_clientes`); crea si no existe, actualiza si existe.
  Nunca crea duplicados.
- **Pedidos**: `online_orders_service.crear_pedido_online(plataforma="woocommerce", referencia_externa="WOO-<id>")`
  — **el MISMO pedido** que desde TPV/Portal Web/Canal Web. NO se crea `PedidoWeb`/`PedidoWoo`/`PedidoMarketplace`.
  Idempotente por referencia externa (no reimporta un pedido ya existente).
- **Stock/Precios (export)**: `db.stock_almacen.stock_total_global` (solo de la empresa) → `PUT /products/{id}`.
- **Estado de pedido**: mapeo ERP→WooCommerce (`PENDIENTE→pending`, `ENVIADO→completed`, …) → `PUT /orders/{id}`.

## Autenticación / validación / secretos

- **Autenticación**: WooCommerce REST API con **Consumer Key/Secret** (nunca almacenados en claro; SecretManager).
- **VALIDAR** comprueba URL, API accesible, credenciales, permisos, **versión WooCommerce** (`system_status`),
  SSL. Actualiza SOLO el **estado existente** del motor (→ `VALIDADA`); no crea estados nuevos.

## Sincronización

- **Inicial**: importa productos/categorías/clientes/pedidos SIN borrar datos existentes; idempotente.
- **Incremental**: usa la **última sincronización** ya existente en el motor (`servicio.obtener(...).ultima_sync`)
  con `modified_after` — nunca reimporta todo. Reutiliza el pipeline/estado del motor (`servicio.sincronizar`).

## Interfaz (Marketplace › Integraciones Comerciales)

El asistente existente (no se modifica su flujo) añade **Consumer Key** y **Consumer Secret** (cifrados vía
SecretManager). Los botones **Validar/Sincronizar** del centro se enrutan al **adaptador real** cuando está
operativo (dirigido por adaptador — `disponible()`+`hasattr`, no `if plataforma==`); si no, caen al estado
simulado. Mismo estilo que el resto.

## Honestidad / degradabilidad

Llamadas REALES (WooCommerce REST API). `disponible()` = True SOLO con URL + Consumer Key/Secret reales. Sin
ellas → `MISSING_CREDENTIALS` sin tocar la red. Las pruebas usan un transporte INYECTADO (costura) para
verificar la orquestación y la reutilización de motores sin red — no es un mock presentado como operativo.

## Pruebas (`test_web15_woocommerce_real.py`, 8)

Registro + degradable · autenticación + validación (versión/SSL) · importación productos/clientes/pedidos
(reutiliza motor: pedido con `plataforma=woocommerce`, mismo `online_orders`) · **idempotencia/sin duplicados**
(re-import no crea copias) · exportación stock/precios (solo de la empresa) · sincronización incremental
(usa última sync) · auditoría `WOO_*` + multiempresa · secretos por SecretManager (cifrados, nunca en claro).
**Suite:** 754 passed, 1 skipped (0 regresiones sobre 746).

## No modificado (§13)

Hostinger · Canal Web · Portal Web · TPV · Marketplace de Plugins · Catálogo · Stock · Caja · RRHH · AWS ·
Terraform · Docker · Entitlements · **motor WEB-13**: intactos. Los motores ERP (catálogo/clientes/pedidos/
stock) se REUTILIZAN, no se modifican.

## Preparado para siguientes fases (§15)

Shopify/PrestaShop/Magento/OpenCart/Amazon/eBay/Miravia/AliExpress/TikTok Shop = replicar EXACTAMENTE este
patrón (adaptador + transporte inyectable + SecretManager + reutilización de los mismos motores ERP + estados/
pipeline del motor), con esfuerzo mínimo y sin tocar el núcleo. Cada plataforma en su propia fase.
