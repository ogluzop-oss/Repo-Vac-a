# INFORME — Refactorización Canal Web (Fase WEB-02)

Fecha 2026-07-29. Refactor **aditivo** que convierte el Canal Web en el ORQUESTADOR del ecosistema web y
prepara Hostinger (creación de web) e Integraciones Comerciales (Marketplace), sin implementar integraciones
reales. N7, compatibilidad hacia atrás, 0 regresiones. Regresión: **687 passed, 1 skipped** (682 → +5).

## Cambios realizados (todos NUEVOS ficheros — nada existente modificado)

| Fichero (nuevo) | Rol |
|---|---|
| `services/comercio_digital/canal_web/orquestador.py` | Asistente inicial: `flujo_inicial`/`elegir`/`escenario_recomendado`/`tiene_web`/`registrar_web_creada`. Decide NO→Hostinger / SÍ→Marketplace. Reutiliza el servicio Canal Web |
| `services/comercio_digital/canal_web/proveedores/{base,hostinger,__init__}.py` | Abstracción `ProveedorWeb` + `HostingerProvider` (oficial, **PREPARADO/no operativo**, sin API/OAuth) |
| `services/comercio_digital/integraciones_comerciales/{base,catalogo,__init__}.py` | Arquitectura que Marketplace asumirá: contrato `ConectorComercial` + catálogo de plataformas (Woo/Shopify/Presta/Magento/OpenCart/Amazon/eBay/Miravia/AliExpress/TikTok), todo `PREPARADO` |
| `gui/canal_web_gui.py` | Ventana de entrada con el asistente "¿Tiene web?" → Hostinger (crear) / redirección a Marketplace › Integraciones Comerciales. Autónoma (no importa helpers de `tpv.py`) |
| `tests/unit/test_canal_web_web02.py` | 5 tests (orquestador, Hostinger preparado, integraciones, GUI offscreen) |

## Nuevo flujo (implementado como arquitectura)

```
Usuario → Canal Web (orquestador) → ¿Tiene web?
   NO → Crear web con Hostinger (proveedor oficial, PREPARADO) → registrar_web_creada → sync (servicio Canal Web)
   SÍ → Marketplace › Integraciones Comerciales → (Marketplace) elegir plataforma → conectar → sync
```

El Canal Web **sólo decide y redirige**. Hostinger crea la web. Marketplace realiza la integración comercial.

## Lo que se MANTIENE intacto (N7, sin romper contratos)

Canal Web Service (`existe/estado/crear/actualizar_config/publicar/despublicar/regenerar/sincronizar/metricas/
panel`), `web_config` (fuente única de marca), publicación, sincronización, pickup, métricas, transacciones,
auditoría e integraciones con artículos/pedidos/clientes/empresas/tiendas. **0 contratos públicos alterados.**

## WooCommerce / Shopify

- La auditoría (grep) confirma que el diálogo de Canal Web **NO contenía** configuración Woo/Shopify: éstas
  viven en el **Escenario A** (`db/ecommerce.py`/`services/tpv/ecommerce/*`), separado de la web propia
  (Escenario B/`web_config`). Por tanto **no hay Woo/Shopify que eliminar del Canal Web**.
- La responsabilidad de esas plataformas se reubica CONCEPTUALMENTE en **Integraciones Comerciales**
  (Marketplace): se crea su arquitectura/catálogo PREPARADO **sin tocar `services/marketplace/*`** ni
  implementar integraciones, y **sin borrar** `db/ecommerce.py` (reutilizable; se reaprovechará al implementar).

## Extracción de la config del Canal Web fuera del TPV — PENDIENTE (documentado, por Strangler)

- **Hallazgo**: el diálogo embebido `gui/tpv.py::_CanalWebConfigDialog` **depende de helpers privados de
  `tpv.py`** (`_btn`, `_lbl`, `_QScrollArea`, `_RoundTableCorners`, `_ss_tabla_neon`). Un traslado físico
  íntegro arrastraría esos helpers compartidos y sus tests de integración → **alto riesgo de regresión**.
- **Decisión (regla del proyecto — CLAUDE.md · Strangler + deprecación)**: NO se hace un big-bang. Se crea la
  **nueva entrada** (`gui/canal_web_gui.py`) como reemplazo autónomo; el diálogo antiguo queda para retirada
  progresiva cuando el nuevo flujo lo sustituya y no queden referencias. **`tpv.py` NO se ha modificado**
  (respeta "NO modificar TPV"); la extracción física se completará en una iteración de migración incremental.
- **Estado honesto**: el criterio "el TPV no debe contener configuración del Canal Web" **aún no se cumple
  físicamente**; queda la ruta de sustitución preparada. No se fuerza una extracción arriesgada.

## Auditoría / compatibilidad

- Cambios 100% aditivos; `git status` de `tpv.py`/`ecommerce.py`/`catalogo_gestion.py` muestra `M` por trabajo
  **previo** (árbol sin commitear desde `fe7ab9d`), NO por esta fase.
- Módulos NO tocados: Marketplace, Catálogo, Portal, Stock, TPV, Caja, Facturación, Logística, Usuarios,
  Empresas, Tiendas, RBAC, Auditoría, Entitlements.
- 0 integraciones reales (Hostinger/plataformas = PREPARADO). Multiempresa (id_empresa en todo el orquestador).

## Pendiente para la siguiente iteración

1. Extraer físicamente `_CanalWebConfigDialog` de `tpv.py` a `gui/canal_web_gui.py` (recolocando/aislando los
   helpers UI compartidos) — Strangler, con validación de la suite.
2. Cablear la nueva entrada Canal Web en el menú (ruta `v_id`) + el callback `on_ir_marketplace`.
3. Alojar "Integraciones Comerciales" dentro de la GUI de Marketplace (cuando se aborde Marketplace).
4. Implementar Hostinger real (API/OAuth/registro/sync) y los conectores comerciales — fases posteriores.

**FASE WEB-02 (arquitectura) COMPLETADA con la extracción física del TPV documentada como paso Strangler
siguiente. 0 regresiones, 0 integraciones reales, 0 contratos rotos.**
