# CERTIFICACIÓN ARQUITECTÓNICA

## Rearquitectura del Comercio Digital — Catálogo · Canal Web · Marketplace

**Proyecto:** Redefinición funcional de Catálogo, Canal Web y Marketplace (Smart Manager AI Enterprise 1.0).
**Alcance:** reorganización de responsabilidades — aditiva, reversible, multiempresa/multitienda, auditada,
sin motores paralelos (N7), sin romper compatibilidad y sin regresiones.
**Resultado global de la suite:** `520 passed, 1 skipped`.

---

## 1. Fases ejecutadas

| Fase | Objetivo | Estado |
|---|---|---|
| 1 | Catálogo → PIM (identificar/acotar responsabilidades ajenas) | ✅ Cerrada |
| 2 | Canal Web = centro único de la presencia digital (editor único de la marca) | ✅ Cerrada |
| 3 | Marketplace → App Store de Plugins y Extensiones (sin ambigüedad e-commerce) | ✅ Cerrada |
| 4 | Integración y eliminación de duplicidades (fuente única `web_config`) | ✅ Cerrada |
| 5 | Certificación arquitectónica | ✅ Este documento |

---

## 2. Verificación de invariantes (con evidencia de código)

| Invariante | Veredicto | Evidencia |
|---|---|---|
| **Un único propietario por dato** | ✅ | El único escritor de `web_config` es Canal Web (`canal_web.guardar_presencia` y `canal_web._sync_web_config` vía `web_tienda.guardar_config`). Catálogo `_guardar_web` es no-op. |
| **Catálogo sin infraestructura** | ✅ | `catalogo_gestion.py` no importa dominios/DNS/hosting/publicación/pago/sync/pickup; solo redirección *lazy* a Canal Web. |
| **Canal Web sin datos maestros** | ✅ | `canal_web/` no importa `db.catalogo` ni CRUD de producto/categoría/marca. |
| **Marketplace sin lógica de negocio** | ✅ | `services/marketplace/` solo depende de `src.sdk`, `db.marketplace_*` y Event Bus; sin ventas/pedidos/comercio. |
| **N7 (sin motores paralelos)** | ✅ | `canal_web.descriptor().motor_nuevo == False`. Rearquitectura con **0 migraciones/tablas nuevas** (se reutilizan `web_config`, `cd_canal_web`, `web_tienda`, Plugin SDK). |
| **Reutilización completa** | ✅ | Fase 2 y 4 reutilizan `db/web_tienda.py`; Fase 3 conserva el Plugin SDK. Sin duplicar motores. |
| **Compatibilidad hacia atrás** | ✅ | Firmas públicas, `v_id` (`catalogo`/`marketplace`), rutas, tablas y adaptadores intactos. Cambios de presentación/deprecación reversibles. |
| **Sin regresiones** | ✅ | Suite `tests/unit`: `520 passed, 1 skipped` (baseline previo 517; +3 tests nuevos de la rearquitectura). |
| **Documentación arquitectónica actualizada** | ✅ | `CLAUDE.md` §"Comercio Digital — RESPONSABILIDADES CONGELADAS" + docstrings `@deprecated`/frontera en `web_tienda`, `ecommerce`, `_TiendaOnlineConfigDialog`, `db.catalogo`. |

---

## 3. Responsabilidades definitivas (congeladas)

- **Catálogo** = PIM (solo producto). La pestaña "Web" es punto de redirección a Canal Web.
- **Canal Web** = único centro de presencia digital. **Fuente única de marca/activación = `web_config`**
  (servida por `backend/storefront.py`); Canal Web es su único editor. `cd_canal_web.config_negocio` es
  metadato operativo, no fuente de marca.
- **Marketplace** = App Store de plugins/extensiones/conectores. Solo instala/administra; la ejecución
  de los conectores pertenece a los módulos consumidores (p. ej. Canal Web).
- **`ecommerce_config`** = Escenario A (plataforma externa), responsabilidad distinta de la web propia
  (Escenario B/`web_config`); no es duplicidad. En uso; consolidación futura fuera de este proyecto.

---

## 4. Duplicidad eliminada

Antes coexistían dos fuentes de la configuración/marca de la web propia (Catálogo `web_config` y Canal Web
`config_negocio`), con riesgo de divergencia (nombre/dominio/estado). Tras la rearquitectura, **`web_config`
es la fuente única**: toda operación del canal (`crear`/`actualizar_config`/`publicar`/`despublicar`) la
mantiene sincronizada. En particular, `despublicar` ahora retira realmente el escaparate (`web_config.activa=0`),
resolviendo una inconsistencia latente.

---

## 5. Cambios (resumen, todos aditivos/reversibles)

- **Servicio `canal_web`:** `+config_presencia` / `+guardar_presencia` / `+_sync_web_config`; cableado en
  `crear`/`actualizar_config`/`publicar`/`despublicar`.
- **GUI `_CanalWebConfigDialog`:** editor "Marca y configuración comercial" (único editor de la marca).
- **GUI Catálogo:** pestaña "Web" → punto de redirección; `_recargar_web`/`_guardar_web` no-op deprecados.
- **Marketplace:** reencuadre a "App Store · Plugins y Extensiones" (etiqueta de menú, icono apps-grid,
  título, subtítulo, docstrings). Lógica intacta.
- **Documentación/deprecación:** `web_tienda`, `ecommerce`, `_TiendaOnlineConfigDialog` (huérfano), `db.catalogo`.
- **Tests:** `+3` (`test_canal_web.py`): presencia editor único, RBAC, fuente única sincronizada.

---

## 6. Certificación

Se **CERTIFICA** que la reorganización del Comercio Digital cumple la arquitectura funcional aprobada:
propietario único por dato, Catálogo sin infraestructura, Canal Web sin datos maestros, Marketplace sin
lógica de negocio, N7 respetado, reutilización completa, compatibilidad hacia atrás y sin regresiones.

**Arquitectura del área de Comercio Digital: CONGELADA.**
