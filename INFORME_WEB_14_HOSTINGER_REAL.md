# INFORME TÉCNICO — FASE WEB-14 · Integración real con Hostinger (primer proveedor)

**Fecha:** 2026-07-30 · **Tipo:** primera integración REAL, implementada EXCLUSIVAMENTE en el adaptador
Hostinger (motor WEB-13 intacto). **Regresiones:** 0 · **Suite:** 740 → **746 passed, 1 skipped** (+6 WEB-14).

## Objetivo

Implementar el adaptador Hostinger operativo: autenticación, creación de web con IA (la genera Hostinger),
descubrimiento del dominio, registro y conexión automática con Smart Manager — reutilizando el motor WEB-13,
el Canal Web y los estados existentes, con secretos vía SecretManager.

## Honestidad (patrón degradable del ERP, como Fiscal/AEAT)

Las llamadas son REALES (HTTP contra la API oficial de Hostinger, `TransporteHostinger` con `requests`),
pero el adaptador es DEGRADABLE: `disponible()` es `True` **solo** con credenciales reales resueltas por el
SecretManager. Sin credenciales (o sin API de partner de Hostinger), NO simula éxito: devuelve errores
canónicos (`MISSING_CREDENTIALS`, …) y `estado="PREPARADO"`. El transporte es INYECTABLE
(`transporte.set_transporte`) — la costura que usan las pruebas para verificar la orquestación sin red (no es
un mock presentado como operativo: el producto real exige credenciales + API de Hostinger).

> **Bloqueo externo (transparencia):** el end-to-end real requiere credenciales de producción y el acceso
> de partner a la API de creación web con IA de Hostinger. El adaptador queda COMPLETO y operativo-ready; la
> activación real depende de ese acceso externo (no falseado).

## Implementación — `…/integraciones_comerciales/hostinger/` (nuevo paquete)

`motor/` **NO se modifica**. El adaptador real se registra vía el punto de extensión público de WEB-13
(`motor.adaptadores.registrar_adaptador`), llamado desde la fachada. Módulos:

| Módulo | Contenido |
|---|---|
| `adaptador.py` | `HostingerAdapter(motor.adaptadores.HostingerAdapter)` — hereda contratos/capacidades/versión WEB-13. Implementa `autenticar` · `crear_web` · `consultar_estado` · `esperar_finalizacion` · `obtener_dominio` · `registrar_web` · `conectar_smart_manager` + orquestador `crear_y_conectar` (emite progreso UX §11). `disponible()` honesto. |
| `transporte.py` | `TransporteHostinger` (HTTP real, `requests`) → errores mapeados a `motor.errores` (AUTH/NETWORK/TIMEOUT/API/RATE_LIMIT). `set_transporte()`/`get_transporte()` (costura). |
| `secretos.py` | Credenciales SOLO por `services.seguridad.secret_manager` (`obtener_secreto`/`cifrar`). Nunca en variables/JSON/texto plano. |
| `auditoria.py` | Eventos `HOSTINGER_AUTH/CREATE/COMPLETE/CONNECTED/REGISTERED/SYNC/ERROR` sobre `log_auditoria`. |
| `__init__.py` | `registrar()` (registra el adaptador en el motor). |

## Flujo (reutiliza servicios existentes)

1. **autenticar** → `GET /v1/account` (real; sin token → `MISSING_CREDENTIALS`). Audita `HOSTINGER_AUTH`.
2. **crear_web** (datos: nombre_empresa/actividad/país/idioma/correo) → `POST /v1/websites/ai`. Hostinger
   genera la web. Audita `HOSTINGER_CREATE`.
3. **esperar_finalizacion** → *poll* `consultar_estado` hasta READY/timeout. Audita `HOSTINGER_COMPLETE`.
4. **obtener_dominio** → descubre dominio/URL/ID externo.
5. **registrar_web** → **Canal Web** `orquestador.registrar_web_creada` (fuente única: `web_config` +
   dominio). Genera el **registro §6** (dominio/URL/fecha/empresa/proveedor/versión/estado/última sync/ID
   externo) con **estados existentes**. Audita `HOSTINGER_REGISTERED`.
6. **conectar_smart_manager** → `canal_web.publicar` + `canal_web.sincronizar` (sincronización inicial con el
   PIPELINE/engine EXISTENTE: catálogo/productos/stock/clientes/pedidos/reservas/C&C). Estado → `SINCRONIZADA`
   + última sync. Audita `HOSTINGER_SYNC` + `HOSTINGER_CONNECTED`. Error → `HOSTINGER_ERROR`.

Smart Manager NO crea HTML/CSS/plantillas/CMS/landing/dominios/SSL: todo lo genera Hostinger.

## UX (§11) — el usuario solo ve

`crear_y_conectar` emite por `on_progreso`: *Crear página web → Hostinger → Esperando creación… → Página web
creada correctamente → Conectando Smart Manager… → Sincronizando datos… → Proceso finalizado*. Cableado en
`gui/canal_web_gui.py` (formulario de 5 datos + botón "Crear y conectar con Hostinger"; degradable si no hay
credenciales). Sin detalles técnicos.

## Estados / secretos / auditoría / multiempresa

- **Estados**: exclusivamente los existentes (`CONFIGURADA`/`VALIDADA`/`SINCRONIZADA`/…). No se crean nuevos.
- **Secretos**: SecretManager (nunca en claro; el registro §6 no contiene el token — verificado por test).
- **Auditoría**: 7 eventos `HOSTINGER_*` canónicos.
- **Multiempresa/multitienda**: `id_empresa`/`usuario` fluyen a todas las operaciones; registros aislados.

## Arquitectura WEB-13 intacta (verificado)

`motor/` (capacidades/pipeline/adaptadores/colas/errores/versiones) sin cambios. El adaptador Hostinger se
registra por el punto de extensión; los tests WEB-13 siguen verdes (Hostinger sin credenciales → `disponible()
=False`, `estado=PREPARADO`, `conectar`/`crear_web_ia` → `NotImplementedError`).

## Pruebas (`test_web14_hostinger_real.py`, 6)

Registro en el motor + contrato WEB-13 intacto · degradable sin credenciales (no toca la red) · flujo completo
con transporte inyectado (UX §11 + registro §6 + estados) · recuperación ante errores (código canónico) ·
multiempresa · auditoría `HOSTINGER_*` + secretos por SecretManager (token nunca en el registro). **Suite:**
746 passed, 1 skipped (0 regresiones).

## No modificado (RESTRICCIONES)

TPV · Portal Web · Marketplace de Plugins · Portal Cliente · Catálogo · Stock · RRHH · Facturación · AWS ·
Terraform · Docker · RBAC · Entitlements · Licencias SaaS · **arquitectura WEB-13**: intactos. Cambios: nuevo
paquete `hostinger/` + registro en la fachada + cableado UX en `canal_web_gui.py` (Canal Web no está
restringido). No se desplegó nada; sin conexiones externas reales en pruebas.

## Preparado para siguientes fases

WooCommerce/Shopify/PrestaShop/Magento/resto = implementar cada `*Connector` con su transporte/OAuth siguiendo
EXACTAMENTE este patrón (adaptador + transporte inyectable + SecretManager + estados/pipeline del motor), sin
tocar el núcleo.
