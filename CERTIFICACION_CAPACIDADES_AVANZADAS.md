# CERTIFICACIÓN — CAPACIDADES AVANZADAS

## Smart Manager AI · Cierre de capacidades avanzadas y validación multiplataforma

> **Principio rector (del propio prompt): NO maquillar, NO mocks, NO declarar "operativo" lo que solo es
> backend, NO declarar "tiempo real" el polling, NO llamar "IA" a una heurística, NO declarar un conector
> activo sin conexión real, NO declarar Canal Web publicado sin despliegue real.**

Leyenda: **🟢 OPERATIVA · 🟡 PARCIAL · 🔵 PREPARADA (backend, no expuesta) · 🟣 ROADMAP · 🔴 NO EXISTE**

---

## RESUMEN EJECUTIVO

De las 8 capacidades avanzadas, **1 es genuinamente completable/verificable en este entorno de desarrollo**
(API pública) y se ha verificado con pruebas reales; **1 tenía una brecha de honestidad** (etiquetar el
origen de la predicción) que se ha corregido; las **6 restantes tienen BLOQUEOS EXTERNOS** (hardware móvil
+ SDKs, proveedor de hosting + DNS, infraestructura cloud real, credenciales/contratos de terceros) que el
prompt **prohíbe falsear**. Para esas, la infraestructura existe y está bien diseñada, pero la activación
"real" depende de recursos externos, no de más código. Este documento las clasifica con honestidad.

**Cambios de esta fase (mínimos, aditivos, N7):** helper `prediccion.heuristicas.motor_activo()` (distingue
heurística vs ML); pruebas nuevas de API pública + IA. **Regresión: 600 passed, 1 skipped (0 regresiones).**
No se creó ningún motor/tabla/permiso nuevo.

---

## 1. IA PREDICTIVA — 🟡 PARCIAL (heurística real + ML enchufable, ahora ETIQUETADO con honestidad)

**Qué existe:** `services/prediccion/` (motor `heuristicas` por defecto = media móvil + proyección lineal,
`Estimador` con nombre, `set_estimador` para enchufar ML), adaptadores de lectura sobre histórico real
(ventas/stock/compras), predicción por dominio (`ventas/stock/compras/riesgos/tendencias/clientes`).
**Prophet ESTÁ instalado**; `informe_reposicion.py` lo usa si está disponible (degradable). XGBoost/sklearn
NO instalados.

**Brecha (honestidad) — CORREGIDA:** el resultado no exponía si venía de ML o de heurística. Añadido
`heuristicas.motor_activo() → {motor, tipo:'heuristica'|'ml', es_ml}`. Regla: por defecto `es_ml=False`
(heurística) — **la UI/SOMA/dashboards no deben llamarlo "IA/ML"**; al enchufar Prophet/XGBoost via
`set_estimador`, `es_ml=True` y el nombre identifica el modelo. Verificado en `test_capacidades_avanzadas`.

**Pendiente (no bloqueado, pero fuera de este alcance mínimo):** pipeline de entrenamiento/validación/
versionado/métricas persistidas y selección automática de modelo por volumen de datos. La arquitectura lo
soporta (`set_estimador`), pero un entrenamiento ML productivo requiere datasets etiquetados y ciclo MLOps.

**Veredicto honesto:** presentar como **"análisis y predicción con estimación heurística; motor de IA/ML
enchufable (Prophet disponible)"**. NO presentar como "IA predictiva ML entrenada" por defecto.

---

## 2. TIEMPO REAL — 🟡 PARCIAL (eventos in-process reales; sin push en red)

**Qué existe:** Event Bus real (`services/eventbus`: `bus.publicar`, event_store, event_registry),
señales Qt (`stock_signals.stock_actualizado`, actualizaciones TPV), scheduler, y **GraphQL subscriptions**
(`api/graphql/subscriptions.py`). En el escritorio, una venta emite evento → actualiza stock → emite señal
→ refresca la UI **en el mismo proceso**: esto es tiempo real legítimo dentro de la app.

**Límite honesto:** NO hay un servidor WebSocket/SSE que empuje cambios a clientes remotos en red; entre
dispositivos distintos la puesta al día sería por sincronización/consulta, no push. El indicador
"conectado/sincronizando/desconectado" para clientes remotos NO existe (no hay clientes remotos aún).

**Veredicto honesto:** "actualización **inmediata dentro de la aplicación** por eventos/señales". NO
prometer "tiempo real entre dispositivos" hasta que exista transporte push en red + clientes.

---

## 3. MULTIPLATAFORMA — Windows 🟢 · macOS/PDA/MDE ⚪ (no verificable) · Móvil 🟣 ROADMAP

**Qué existe:** app de escritorio **PyQt6 real y operativa en Windows**; perfil táctil / TPV táctil;
`services/mobile/` = **solo capa backend REST** (auth/core/networking/sync/push/sesion). **NO existe ningún
cliente nativo** (0 `*.xcodeproj`, 0 `AndroidManifest.xml`, 0 `build.gradle`, 0 `Info.plist`).

**Bloqueo externo:** construir/validar clientes iOS/Android/macOS requiere Xcode/Android Studio + dispositivos
reales, **no disponibles en este entorno**. Por eso NO puede declararse "compatible" más allá de Windows.

| Plataforma | Cliente | Login | MFA | Operaciones | Offline | Sync | Estado |
|---|---|---|---|---|---|---|---|
| Windows | PyQt6 real | ✔ | ✔ | ✔ | parcial | — | 🟢 OPERATIVA |
| macOS | (mismo código Qt) | ? | ? | ? | ? | ? | ⚪ NO VERIFICADA (sin host) |
| Android | — | — | — | — | — | REST | 🟣 ROADMAP (backend listo, sin cliente) |
| iOS | — | — | — | — | — | REST | 🟣 ROADMAP (backend listo, sin cliente) |
| Tablet | Qt táctil | ✔ | ✔ | ✔ | — | — | 🟡 PARCIAL (layout) |
| PDA/MDE | — | — | — | — | — | — | ⚪ NO VERIFICADA (sin hardware) |
| TPV táctil | Qt táctil | PIN | — | ✔ | — | — | 🟢 OPERATIVA |

**Veredicto honesto:** "Windows operativo; API móvil preparada; **apps Android/iOS/macOS = roadmap**".

---

## 4. CANAL WEB — 🟠 DEGRADABLE POR DISEÑO (sin hosting real)

**Qué existe:** `services/comercio_digital/canal_web` (entidad de negocio: estado/dominio/config/marca en
`web_config`, publicar/despublicar, `gestion_dominios`: propio/subdominio/comprado vía Adapter). El código
lo dice **explícitamente**: *"Generación DEGRADABLE / provider-agnostic: **mientras no haya hosting real**,
el canal se genera y…"*.

**Bloqueo externo:** publicación real end-to-end (build → deploy → DNS → TLS → health check) requiere un
**proveedor de hosting + credenciales DNS/registrador**, no presentes. Los estados DRAFT/BUILDING/READY/
PUBLISHED/FAILED/ROLLING_BACK/OFFLINE se pueden modelar, pero PUBLISHED **real** exige despliegue real.

**Veredicto honesto:** "generación de tienda + gestión de dominios/marca preparada; **publicación real
pendiente de proveedor de hosting**". NO mostrar "PUBLISHED" sin despliegue real (el diseño ya lo evita).

---

## 5. CLOUD Y MULTI-REGIÓN — 🟣 PREPARADO, SIN ACTIVAR (explícito en el código)

**Qué existe:** `platform/cloud/` (nodes, cluster, discovery, routing, failover) y `services/saas_global`.
El propio código lo declara: *failover "**PREPARADO, sin activar**"*, discovery "**resuelve el registro en
memoria; mañana, nodos remotos reales**", routing "**no abre puertos… preparación para el Gateway**".

**Bloqueo externo:** routing/failover/replicación/residencia/backups reales requieren **infraestructura
cloud desplegada** (nodos, regiones, red), no disponible aquí.

**Veredicto honesto:** "arquitectura cloud/multi-región **preparada** (topología, roles, discovery en
memoria)". NO declarar "multi-región operativa".

---

## 6. CONECTORES EXTERNOS — 🔵 INFRA REAL / 🟠 sin conexión activa (bloqueo de credenciales)

**Qué existe:** `comercio_digital/conexiones` (registro con **credenciales cifradas por Secret Manager**,
`secret_ref`, adaptadores por canal), Marketplace/Plugin SDK, webhooks salientes con HMAC, `ecommerce`
(WooCommerce/Shopify/Prestashop adaptadores). La infraestructura de integración es **real y segura**.

**Bloqueo externo:** una conexión CONNECTED real con Amazon/eBay/Stripe/PayPal/M365/Gmail exige
**credenciales + contratos/apps OAuth de cada proveedor**, no presentes. El prompt **prohíbe** simular
integraciones. Sin credenciales, el estado honesto es `AUTH_REQUIRED`/`DISCONNECTED`, no `CONNECTED`.

**Veredicto honesto:** "framework de conectores + almacén seguro de credenciales listo; **conexiones reales
al activar credenciales del proveedor**". NO marcar CONNECTED sin conexión real.

---

## 7. API PÚBLICA — 🟢 OPERATIVA (verificada con pruebas reales)

**Qué existe y se ha VERIFICADO:** `services/api_publica` con **OAuth2 client-credentials real**
(`developer.registrar_app` → `oauth.emitir_token` acotado a scopes → `oauth.verificar_scope`), catálogo de
**scopes** (`SCOPES_DISPONIBLES`: read/write:orders, products, customers, …), **OpenAPI 3.0** (`openapi_
publica.documento`), SDKs y portal de desarrollador. Reutiliza la seguridad JWT/API-keys/rate-limit y el
OpenAPI existentes (**API keys M2M separadas del MFA humano**, conforme a la arquitectura MFA congelada).

**Prueba (real, este entorno):** `test_capacidades_avanzadas.py` — registrar app → emitir token → un scope
concedido verifica `True`, uno no concedido `False`, credenciales incorrectas → sin token; documento OpenAPI
3.0 válido. **PASSED.**

**Veredicto honesto:** **OPERATIVA** — consumible por un desarrollador externo (OAuth2 + scopes + OpenAPI),
sin acceder al código. Único matiz: el catálogo de `paths` del OpenAPI depende de lo publicado por la REST
API interna (`src.api.openapi`).

---

## 8. CERTIFICACIÓN FINAL — ESTADO REAL DE CADA PROMESA DEL VÍDEO

| # | Capacidad | Estado | Presentar en el vídeo como |
|---|---|---|---|
| 1 | IA predictiva | 🟡 | "análisis/predicción heurística; IA/ML enchufable (Prophet)" — NO "IA ML entrenada" |
| 2 | Tiempo real | 🟡 | "actualización inmediata en la app por eventos" — NO "tiempo real entre dispositivos" |
| 3 | Multiplataforma | 🟢 Win / 🟣 móvil | "Windows operativo; apps móviles en roadmap; API móvil lista" |
| 4 | Canal Web | 🟠 | "generación y gestión de dominios/marca; publicación real próximamente" |
| 5 | Cloud multi-región | 🟣 | "arquitectura cloud/multi-región preparada" — NO "operativa" |
| 6 | Conectores externos | 🔵/🟠 | "framework de conectores seguro; se conecta al activar credenciales" |
| 7 | API pública | 🟢 | "API pública OAuth2 + scopes + OpenAPI, consumible" ✅ |
| 8 | Seguridad/MFA (transversal) | 🟢 | intacta (RBAC/MFA/WebAuthn/step-up/auditoría) |

---

## LIMITACIONES RESTANTES (honestidad)

- **No se pueden completar en este entorno** (bloqueo externo, no de código): clientes móviles nativos
  (iOS/Android/macOS · SDK+hardware), publicación Canal Web real (proveedor hosting+DNS), cloud multi-región
  real (infra desplegada), conectores CONNECTED reales (credenciales/contratos de terceros).
- **Se ha hecho lo genuinamente posible aquí**: verificar y certificar la **API pública** como operativa;
  **corregir la honestidad de la IA** (origen heurística vs ML). Nada más se ha "activado" porque hacerlo
  sin los recursos externos sería un mock, prohibido por el propio prompt.

## GARANTÍAS

N7 respetado (0 motores/tablas/permisos nuevos). Compatibilidad hacia atrás intacta (TPV/stock/compras/
RRHH/contabilidad/comercio digital/RBAC/MFA/WebAuthn/API keys). **Regresión: 600 passed, 1 skipped.**

**Conclusión:** el vídeo será fiel si presenta **API pública** como operativa, la **IA** como
heurística-con-ML-enchufable, el **tiempo real** como in-app, y **móvil/Canal-Web-publicado/cloud-multi-
región/conectores** como **preparado/roadmap** hasta disponer de los recursos externos. Ninguna de esas
áreas debe presentarse hoy como "operativa real".
