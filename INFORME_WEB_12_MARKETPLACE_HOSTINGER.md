# INFORME TÉCNICO — FASE WEB-12 · Canal Web + Marketplace Integraciones + Hostinger

**Fecha:** 2026-07-30 · **Tipo:** orquestación/integración (N7; sin generador web propio, sin CMS/editor,
sin conexiones reales — todo SIMULADO/PREPARADO). **Regresiones:** 0 · **Suite:** 726 → **731 passed, 1
skipped** (+5 tests WEB-12).

## Objetivo

Definir la arquitectura del Canal Web y del Marketplace › Integraciones Comerciales. Smart Manager NO
genera webs: orquesta/asiste/integra/sincroniza. La creación web se delega a **Hostinger** (proveedor
oficial); la integración con plataformas ecommerce vive en Marketplace.

## 1. Arquitectura implementada

### Canal Web (`gui/canal_web_gui.py`, reescrito)
- Al entrar muestra **ÚNICAMENTE** la pregunta: *«¿Tu empresa ya dispone de una página web?»* (Sí/No).
- **Sí** → redirige **automáticamente** a Marketplace › Integraciones Comerciales (callback `on_ir_marketplace`
  cableado por el menú, o abre `IntegracionesComercialesWindow` directamente). El usuario no navega a mano.
- **No** → asistente de **creación con IA (Hostinger)**: flujo SIMULADO de 6 pasos (Bienvenida → Crear página
  web → Hostinger IA → Configuración inicial → Creación completada → Conectar automáticamente). En el paso
  "Crear" invoca el proveedor Hostinger PREPARADO (`proveedores.oficial()`, `disponible()=False`). Nada
  conectado. Explica que Hostinger genera la web con IA y que Smart Manager solo conectará el ERP.
- Se retira de la pregunta inicial cualquier otra opción (el acceso a la configuración de marca se conserva
  vía Catálogo/Portal Web — `_abrir_config` intacto por compatibilidad).

### Marketplace › Integraciones Comerciales
- **Servicio** (`services/marketplace/integraciones_comerciales/servicio.py`, ampliado): nuevas
  `validar()` y `sincronizar()` **SIMULADAS** (transiciones del modelo de estados existente; sin HTTP/OAuth/
  API/webhooks) + constante `AMBITOS_SYNC` (productos/clientes/pedidos/reservas/stock/precios/estados/
  Click&Collect). Auditan `INTEGRACION_VALIDADA`/`INTEGRACION_SINCRONIZADA`. Expuestas en la fachada.
- **GUI** (`gui/integraciones_comerciales_gui.py`, nuevo): centro operativo que lista las 10 plataformas con
  **estado · última sync · versión · habilitada** y ofrece **Configurar · Validar · Sincronizar · Eliminar ·
  Añadir**. Asistente de alta inline: Seleccionar plataforma → URL → **referencia** de credenciales →
  Guardar (`crear_integracion`) → Validar (simulado) → Sincronizar (simulado) → Finalizado.

## 2. Componentes REUTILIZADOS (N7)

- `services/comercio_digital/canal_web/orquestador` (decisión Sí/No), `.../proveedores` (Hostinger oficial
  PREPARADO), catálogo de plataformas `comercio_digital.integraciones_comerciales`.
- `services/marketplace/integraciones_comerciales`: `estados` (7 canónicos, sin crear otros), `modelo`
  (`Integracion` con `credenciales_ref` — nunca el secreto), `servicio` (CRUD + habilitar/deshabilitar),
  auditoría `log_auditoria`. Aislamiento multiempresa por `id_empresa`.

## 3. Componentes PREPARADOS (sin ejecutar)

- **Creación web con Hostinger**: flujo simulado completo; proveedor `disponible()=False` (sin API/OAuth).
- **Conexión automática** tras la creación: arquitectura declarada (Empresa → Dominio → Canal Web → Catálogo
  → Pedidos → Reservas → Click&Collect → Clientes → Stock). No implementada.
- **Sincronización**: `AMBITOS_SYNC` preparados; `sincronizar()` solo transiciona estados (no ejecuta).
- **Secretos**: solo `credenciales_ref` (nombre del secreto en Secret Manager). Nunca tokens/API keys/OAuth/
  contraseñas en claro.

## 4. Estados (existentes, sin crear otros)

`NO_CONFIGURADA · CONFIGURADA · VALIDADA · SINCRONIZANDO · SINCRONIZADA · ERROR · DESHABILITADA` con las
transiciones ya definidas (`estados._TRANSICIONES`). Validar sin `credenciales_ref` → ERROR (simulado).

## 5. Plataformas soportadas (catálogo existente, extensible)

WooCommerce · Shopify · PrestaShop · Magento · OpenCart · Amazon · eBay · Miravia · AliExpress · TikTok Shop.
Añadir una nueva = una entrada en el catálogo (sin tocar la GUI ni el servicio).

## 6. Verificaciones (enunciado)

- [x] Canal Web solo hace la pregunta inicial. [x] "Sí" redirige automáticamente al Marketplace. [x] "No"
  abre el asistente de Hostinger (6 pasos simulados). [x] Hostinger es solo proveedor externo (no CMS/editor/
  dominios/hosting en Smart Manager). [x] Marketplace operativo (listar/configurar/validar/sincronizar/
  eliminar/añadir). [x] Integraciones reutiliza la arquitectura existente. [x] Sincronización simulada.
  [x] Estados correctos. [x] Multiempresa (aislamiento por `id_empresa`). [x] N7. [x] 0 regresiones.

## 7. Pruebas

- `test_web12_marketplace_integraciones.py` (5): flujo de pregunta + Hostinger 6 pasos; servicio validar/
  sincronizar simulados + estados + secretos por referencia; aislamiento multiempresa; GUI operativa (lista
  10 plataformas + asistente de alta → SINCRONIZADA); N7 sin duplicación (sin clientes HTTP).
- `test_canal_web_web02` actualizado al nuevo flujo; `test_integraciones_comerciales_web03` verde.
- **Suite completa:** 731 passed, 1 skipped (0 regresiones sobre 726).

## 8. No modificado (PROHIBIDO)

TPV · Portal Cliente · **Portal Web para empleados** · **Marketplace de Plugins** (extensiones) · Catálogo ·
Facturación · Caja · RRHH · Producción · AWS · Terraform · Docker · RBAC · Entitlements · Licencias SaaS:
**intactos**. Contratos públicos y compatibilidad hacia atrás conservados.

## 9. Pendiente para futuras fases (WEB-13/14/15)

- **WEB-13** (Dashboard Ejecutivo): agregación de KPIs del ecosistema web.
- **WEB-14/15**: conectores REALES por plataforma (API/OAuth/webhooks) sobre los contratos `ConectorPreparado`;
  ejecución REAL de la sincronización por ámbito; integración real de Hostinger (creación web + vinculación
  automática Empresa→…→Stock); persistencia de integraciones (reutilizando `db/ecommerce.py`, sin secretos).
