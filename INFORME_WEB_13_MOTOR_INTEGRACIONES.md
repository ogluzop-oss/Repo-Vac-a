# INFORME TÉCNICO — FASE WEB-13 · Motor Enterprise de Integraciones Comerciales

**Fecha:** 2026-07-30 · **Tipo:** EXCLUSIVAMENTE arquitectónica (nada conectado: sin OAuth/API Keys/HTTP/
webhooks/polling/colas reales/sincronización). **Regresiones:** 0 · **Suite:** 731 → **740 passed, 1
skipped** (+9 tests WEB-13).

## Objetivo

Dotar a `services/marketplace/integraciones_comerciales` de un motor **desacoplado y dirigido por
CAPACIDADES** para admitir cualquier plataforma futura sin rediseñar Smart Manager. Las fases WEB-14/15/16…
solo implementarán los adaptadores concretos, sin tocar esta arquitectura.

## Estructura creada — `…/integraciones_comerciales/motor/`

| Módulo | Contenido (todo PREPARADO, sin conexión) |
|---|---|
| `capacidades.py` | `ConnectorCapabilities` (14 flags `supports_*`) + matriz declarativa por plataforma + `capacidades()`/`matriz()`/`registrar()`. La arquitectura decide **por capacidades**, nunca ramificando por plataforma. |
| `pipeline.py` | `PASOS = (VALIDAR, AUTENTICAR, DESCUBRIR, IMPORTAR, SINCRONIZAR, VERIFICAR, FINALIZAR)`; `PipelineSincronizacion.plan()` calcula los ámbitos **según capacidades**; `ejecutar()` eleva `NotImplementedError`. |
| `importacion.py` | Interfaces separadas: productos/clientes/pedidos/stock/precios/estados/transportistas/reservas/click_collect (todas `NotImplementedError`). |
| `exportacion.py` | actualizar_stock/crear_pedidos/actualizar_pedidos/actualizar_estados/actualizar_clientes/actualizar_precios (`NotImplementedError`). |
| `colas.py` | `ColaTrabajos` (contrato) + `ColaLocal` (en memoria, utilidad) + `ColaRedis`/`ColaSQS`/`ColaRabbitMQ` PREPARADAS (`NotImplementedError`); factoría `cola(backend)` por registro. |
| `deteccion.py` | `detectar(url, señales)` por FIRMAS declarativas; **NO accede a la red** (sin señales → `requiere_sondeo`). |
| `validacion.py` | `Validador` con comprobaciones `url/credenciales/version/api/permisos/estado/ssl` → informe `PREPARADO` (no valida realmente). |
| `errores.py` | `CodigoError` (9: AUTH/NETWORK/TIMEOUT/API/RATE_LIMIT/UNSUPPORTED_VERSION/INVALID_CONFIGURATION/INVALID_DOMAIN/MISSING_CREDENTIALS) + `IntegracionError` (definido, **no se lanza**). |
| `versiones.py` | `VersionInfo` (api/connector/minimum/maximum) + `compatible()`. |
| `adaptadores.py` | `AdaptadorConector` base (capacidades+versión+validador+pipeline, `disponible()=False`) + `HostingerAdapter` (crear_web_ia/publicar/dominio/ssl/info_web/conectar_smart_manager, preparados) + `WooCommerce/Shopify/PrestaShop/Magento/OpenCart/Amazon/eBay/Miravia/AliExpress/TikTokShop` (vacíos). Registro `ADAPTADORES` + `adaptador()`. |
| `auditoria.py` | Eventos canónicos `INTEGRATION_CREATED/VALIDATED/SYNC_STARTED/SYNC_FINISHED/DISABLED/ENABLED` sobre `log_auditoria` (N7, sin motor de eventos nuevo). |

Fachada `integraciones_comerciales/__init__.py` ampliada: expone `motor`, `capacidades`, `adaptador`,
`ConnectorCapabilities` (compatibilidad hacia atrás intacta).

## Componentes REUTILIZADOS (N7)

`contratos.py` (ConectorMarketplace/Productos/Pedidos/Clientes/Inventario/Precios), `conector.py`
(`ConectorPreparado`), `estados.py` (7 estados), catálogo de plataformas, `log_auditoria`. El motor **compone**
sobre ellos (no duplica).

## Componentes PREPARADOS para futuras fases

- **WEB-14 (Hostinger real)**: implementar `HostingerAdapter` (creación IA/dominio/SSL/publicación/info +
  `conectar_smart_manager`: Empresa→Dominio→Canal Web→Catálogo→…→Stock).
- **WEB-15 (WooCommerce)/WEB-16 (Shopify)/resto**: implementar cada `*Connector` (validación real, import/export,
  pipeline `ejecutar()`), sin tocar el motor.
- **Colas reales** (Redis/SQS/RabbitMQ), **detección con sondeo**, **validaciones reales** — todos con contrato
  ya definido.

## Prohibiciones respetadas (verificadas por test sobre el código fuente)

- Sin `if plataforma ==` (todo por capacidades/registros).
- Sin clientes HTTP/OAuth/websockets (sin `import requests/urllib/httpx/aiohttp/oauthlib/websocket`).
- Sin webhooks/polling/workers/sincronización real. Colas remotas y pipelines elevan `NotImplementedError`.
- Secretos: las colas remotas guardan solo `config_ref`; nunca credenciales en claro.

## Multiempresa / multitienda

El motor es **stateless por tenant**: capacidades/versión/adaptadores son metadatos por plataforma; el estado
por empresa vive en `servicio.py` (aislado por `id_empresa`, ya existente). La ejecución futura recibirá
`id_empresa`/`id_tienda` en import/export/pipeline.

## Pruebas

- `test_web13_motor_integraciones.py` (9): capacidades por conector; pipeline por capacidades (Hostinger sin
  ámbitos de datos, Woo con todos); import/export separados y preparados; colas (local funcional, remotas
  `NotImplementedError`); detección sin red; validación/errores/versiones; 11 adaptadores preparados
  (`disponible()=False`); auditoría canónica; y las prohibiciones arquitectónicas (grep del motor).
- **Suite completa:** 740 passed, 1 skipped (0 regresiones sobre 731).

## No modificado (PROHIBIDO)

TPV · Portal Web · Canal Web · Marketplace de Plugins · Catálogo · Portal Cliente · AWS · Terraform · Docker ·
RBAC · Entitlements · Licencias SaaS: **intactos**. Único cambio fuera del nuevo `motor/` = ampliación aditiva
de la fachada `integraciones_comerciales/__init__.py`. No se desplegó nada ni se realizaron conexiones externas.
