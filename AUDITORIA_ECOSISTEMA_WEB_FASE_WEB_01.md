# AUDITORÍA MAESTRA DEL ECOSISTEMA WEB — FASE WEB-01

Fecha 2026-07-29. **Solo análisis y documentación. No se modificó, movió, renombró ni creó nada.** Auditoría
del ecosistema web previa a su reorganización en 4 bloques (Portal Back Office · Canal Web · Marketplace ·
Catálogo).

---

## 1. Estado actual del CANAL WEB

Existe y está **bien definido**, en dos capas complementarias (N7, sin motores paralelos):

### 1.a Servicio de negocio — `src/services/comercio_digital/canal_web/`
Representa el CANAL WEB como entidad completa: ¿existe?, estado, dominio, configuración de negocio,
publicación, regeneración, sincronización y métricas. **Compone** infraestructura existente:
- `comercio_digital/conexiones` — endpoint + credenciales CIFRADAS (Secret Manager); la generación crea/
  actualiza la conexión "web" automáticamente (el usuario no introduce endpoint/token).
- `comercio_digital/publicaciones` + `comercio_digital/catalogo` + `sync` — catálogo publicado y sync.
- `pickup` / `transacciones` / `pedidos_online` — métricas (pedidos, reservas Click&Collect).
- Event Bus (`CanalWeb*`), RBAC (`canal_web.*`), auditoría, `gobernanza`. `gestion_dominios.py` (dominios).
- **Fuente ÚNICA de marca/activación = `web_config`** (`db/web_tienda.py`); Canal Web es su **único editor**
  (`_sync_web_config`). Generación **DEGRADABLE / provider-agnostic** (sin hosting real todavía — Fable 5).

### 1.b Storefront (frontend web) — `src/backend/storefront.py`
Tienda online propia (**Escenario B**) servida por Flask. Rutas: `/tienda/<id_empresa>`,
`/tienda/<id_empresa>/categoria/<slug>`, `/producto/<slug>`, `/buscar`. Multi-tenant (empresa en la URL),
HTML por funciones puras (testeable sin servidor). Consume el catálogo **EN VIVO** (`services.catalogo`, vista
pública) + `web_config` (marca). Registrado como blueprint en `backend/app.py`.

### 1.c UI de administración
Vive **dentro de `src/gui/tpv.py`** (`_CanalWebConfigDialog`, invocado desde `tpv.py:4813`). ⚠️ Acoplamiento:
la administración del Canal Web está embebida en la ventana TPV (fichero grande).

### 1.d Escenario A (plataforma externa) — `db/ecommerce.py` (`ecommerce_config`)
Conexión a WooCommerce/Shopify/Prestashop. Responsabilidad **DISTINTA** de la web propia (Escenario B/
`web_config`), NO duplicidad. En uso por `services/tpv/ecommerce/*`.

**Función real:** presencia digital propia (generación/publicación/dominios/marca) + storefront público.

---

## 2. Estado actual del MARKETPLACE

`src/services/marketplace/` (~842 LOC) + `src/gui/marketplace_gui.py` + migr `0134_marketplace`.

**Objetivo real: App Store de PLUGINS y extensiones** (reutiliza el Plugin SDK). `servicio.py` orquesta:
`catalogo` (plugins) + `validacion` + `firmas` + `dependencias` + `licencias` + `instalacion` + `actualizacion`
+ `repositorios`, aplicando la POLÍTICA por empresa (`oficiales|firmados|internos|todos`, `marketplace_politica`).
Punto único que consumen GraphQL y GUI. Multiempresa estricto.

**NO es un canal de venta ni gestiona negocio** — solo instala/administra plugins; la ejecución de cada conector
vive en su módulo consumidor (p. ej. Canal Web). **Responsabilidad limpia, sin mezcla.**

---

## 3. Estado actual del CATÁLOGO

Hay **cinco** módulos llamados `catalogo`, con **dominios DISTINTOS** (documentado como NO duplicidad en
`db/catalogo.py` y CLAUDE.md). Tres son relevantes para comercio, dos no:

| Módulo | Dominio | Rol |
|---|---|---|
| `db/catalogo.py` | **PIM** (datos maestros de producto, overlay sobre `articulos`) | Fuente de la ficha web; `articulos.codigo` = única fuente de stock/precio |
| `services/catalogo/service.py` | **Serialización por rol** | Web pública (oculta stock/almacenes) vs panel interno; `serializar(interno=)` |
| `services/comercio_digital/catalogo/` | **Ficha comercial COMPUESTA** (i18n/divisa/IVA/reglas) | Capa de composición/LECTURA para canales (Dominio→Adaptador→Canal) |
| `services/marketplace/catalogo.py` | **Catálogo de PLUGINS** (App Store) | Ajeno al comercio |
| `services/seguridad/catalogo.py` | **Catálogo de permisos RBAC** | Ajeno (colisión de nombre) |
| `services/autonomia/catalogo.py` | **Catálogo de acciones de autonomía** | Ajeno |

**GUI:** `gui/catalogo_gestion.py` = gestión **PIM** (ficha web, categorías, marcas, SEO, visibilidad web); la
antigua pestaña "Web" **redirige a Canal Web** (`_abrir_canal_web`).

**¿Duplica Canal Web / Stock / Marketplace?** NO en código: los 3 `catalogo` de comercio son **capas** (datos →
serialización → composición), no duplicados. El stock vive SOLO en `articulos` (el catálogo lo referencia). El
`marketplace.catalogo` es de plugins (dominio distinto). **Riesgo real = confusión por el nombre**, no
duplicación funcional. *(Sin emitir decisión, según lo pedido.)*

---

## 4. ¿Existe un PORTAL WEB para EMPLEADOS (Back Office)?

**NO existe un módulo WEB de Back Office para empleados.** Lo que hay:

- `src/services/portal/` (~144 LOC, Fase V): **infraestructura** de portales por TIPO
  (`cliente/proveedor/transportista/empleado/asesoria/auditor`) + `SCOPES` (mínimo privilegio) + `acceso.py`
  (control + auditoría). Descrito como "servido por REST/GraphQL", pero **NO está cableado a ningún router
  REST/backend** y **no tiene frontend web**.
- `src/gui/portal_empleado.py`: **Portal del Empleado de ESCRITORIO** (PyQt), autoconsulta RRHH sobre
  `rrhh.portal_servicio`. No es web.
- `src/services/facturacion/portal_cliente.py`: servicio de portal de facturas de CLIENTE (backend).

**Conclusión:** hoy no hay Back Office WEB para empleados; existe una base (tipos/scopes de `services/portal`,
API REST/GraphQL, `services.catalogo` con vista interna) pero **sin frontend web ni wiring del portal**.

---

## 5. Relaciones entre módulos (mapa)

```
Storefront (backend/storefront)  ── consume ─▶ services.catalogo (vista pública) ─▶ db.catalogo (PIM) ─▶ articulos (stock/precio)
        │                          └─ consume ─▶ db.web_tienda (web_config = marca)
        ▼
Canal Web (comercio_digital/canal_web) ── compone ─▶ conexiones + secret_manager + publicaciones
        │                                └─ compone ─▶ comercio_digital.catalogo (ficha comercial) + sync
        │                                └─ métricas ─▶ pickup / transacciones / pedidos_online
        │                                └─ edita ────▶ web_config (_sync_web_config)   · Event Bus · RBAC canal_web.*
        ▼
comercio_digital (checkout/pagos/envios/pickup/inventario/transacciones)  ── integra ─▶ pedidos_online, clientes, articulos, facturación, logística
UI Canal Web = gui/tpv.py::_CanalWebConfigDialog     UI Catálogo = gui/catalogo_gestion (PIM)     UI Marketplace = gui/marketplace_gui

Marketplace (services/marketplace) ── reutiliza ─▶ Plugin SDK + repositorios + firmas/licencias/dependencias   (independiente del comercio)

Portal (services/portal)  ── define tipos/scopes ──▶ (SIN router REST ni frontend)     Portal empleado = gui/portal_empleado (ESCRITORIO, RRHH)
```

REST/GraphQL: `api/routers/commerce.py` (descriptor + health), `api/graphql/queries.py|mutations.py`.

---

## 6. Dependencias detectadas

- **Storefront → services.catalogo → db.catalogo → articulos** (cadena de datos; stock/precio única en `articulos`).
- **Storefront → db.web_tienda (web_config)** para la marca.
- **Canal Web → conexiones, secret_manager, publicaciones, comercio_digital.catalogo, sync, pickup,
  transacciones, pedidos_online, eventbus, rbac, gobernanza, web_tienda** (composición amplia; N7).
- **comercio_digital.catalogo → publicaciones (PPL) + capabilities(divisas/fiscalidad/rules)**.
- **Marketplace → Plugin SDK/repositorios** (aislado del comercio).
- **Portal (infra) → RBAC/auditoría**; **portal_empleado → rrhh.portal_servicio** (+ reutiliza helpers de
  `catalogo_gestion`, acoplamiento GUI menor).
- **UI Canal Web → tpv.py** (acoplamiento a la ventana TPV).

No se detectaron **dependencias circulares** de servicio (el flujo es en capas: articulos → catalogo →
storefront/canal). El único acoplamiento estructural relevante es **la UI de Canal Web embebida en `tpv.py`**.

---

## 7. Duplicidades detectadas

- **Ninguna duplicidad de código funcional.** Las coincidencias son de **NOMBRE**: 5 módulos `catalogo` con
  dominios distintos (PIM / serialización / ficha comercial / plugins / RBAC / autonomía). Documentado como
  intencional. **Riesgo = confusión de desarrolladores**, no duplicación.
- **Escenario A (`ecommerce_config`) vs Escenario B (`web_config`)**: responsabilidades distintas (plataforma
  externa vs web propia), NO duplicidad.
- Dos "portales de empleado" con propósitos distintos: `services/portal` (infra genérica multi-tipo) y
  `gui/portal_empleado` (escritorio RRHH). No se solapan funcionalmente hoy.

---

## 8. Funcionalidades compartidas

- **`db.catalogo` (PIM)** y **`services.catalogo` (serialización por rol)** las comparten storefront (web
  pública), panel operativo (`catalogo_gestion`) y conectores e-commerce.
- **`web_config`** (marca/activación) compartida por storefront (sirve) y Canal Web (edita) — fuente única.
- **articulos** = única fuente de stock/precio para todo el comercio.
- **Event Bus / RBAC / auditoría / secret_manager / capabilities(divisas/fiscalidad/rules)** transversales.

---

## 9. Código reutilizado

- Canal Web reutiliza toda la infra de `comercio_digital` (conexiones/publicaciones/sync/pickup/transacciones)
  + secret_manager + eventbus — **no reimplementa** nada (N7).
- Storefront reutiliza `services.catalogo` en vivo (sin export que regenerar).
- Marketplace reutiliza el Plugin SDK/repositorios.
- `portal_empleado` reutiliza `rrhh.portal_servicio` y helpers de `catalogo_gestion`.
- `services.catalogo.serializar(interno=)` es el punto único que separa vista pública vs interna.

---

## 10. Riesgos de la futura separación

| Riesgo | Detalle | Severidad |
|---|---|---|
| UI Canal Web en `tpv.py` | Para un bloque "Canal Web" independiente, `_CanalWebConfigDialog` debe extraerse de la ventana TPV | Media |
| Confusión de `catalogo` | 5 módulos homónimos; separar "Catálogo" como bloque requiere clarificar fronteras/naming sin romper contratos públicos | Media (organizativa) |
| Back Office web inexistente | El Portal de empleados web es **greenfield**; `services/portal` no tiene router ni frontend | Media (trabajo nuevo, no bloqueo) |
| Marca única `web_config` | Cualquier separación debe mantener Canal Web como editor único de `web_config` (N7) | Baja (respetando la regla) |
| Multi-tenant | Todo aislado por `id_empresa`; la separación no debe introducir fugas cross-tenant | Baja (patrón ya sólido) |
| Storefront = único frontend web | Separar Portal/Canal exige decidir framework/hosting del frontend (hoy Flask+HTML puro; degradable) | Media (dependía de hosting real) |

---

## 11. Recomendaciones técnicas para la siguiente fase (sin implementar)

1. **Marketplace**: ya está limpio y aislado (servicio + GUI + migr) → **separable de inmediato** como bloque.
2. **Canal Web**: extraer la UI (`_CanalWebConfigDialog`) de `tpv.py` a su propio módulo GUI; el servicio
   (`comercio_digital/canal_web`) ya es un bloque autónomo. Mantener `web_config` como fuente única de marca.
3. **Catálogo**: NO fusionar ni renombrar a la ligera (contratos públicos). Documentar/formalizar las 3 capas
   de comercio (PIM `db.catalogo` → serialización `services.catalogo` → ficha comercial
   `comercio_digital.catalogo`) y aclarar que `marketplace.catalogo`/`seguridad.catalogo`/`autonomia.catalogo`
   son dominios ajenos. Evaluar un namespacing lógico para reducir confusión.
4. **Portal Back Office (empleados)**: es **nuevo**. Reutilizar `services/portal` (tipo `empleado` + scopes) +
   exponerlo por REST/GraphQL (hoy sin router) + `services.catalogo` (vista interna) + servicios existentes
   (RRHH/documentos/workflow/CCP). Definir frontend/hosting.
5. **Frontend/hosting**: la presencia web real (storefront/portal) sigue **degradable** sin hosting; decidir
   proveedor antes de construir el Back Office web.
6. **Aislamiento multi-tenant**: conservar `id_empresa` en toda ruta/servicio nuevo; reutilizar RBAC/scopes.

---

## Conclusión

El ecosistema web está **razonablemente modularizado y sin duplicación de código**: Canal Web (servicio sólido +
storefront + UI acoplada a TPV), Marketplace (App Store de plugins, aislado), Catálogo (3 capas de comercio +
2 homónimos ajenos, documentado como no-duplicidad) y **sin Back Office web de empleados** (solo infra de
portal sin frontend + portal de escritorio RRHH). La separación en 4 bloques es **viable**; los principales
trabajos previos son: extraer la UI de Canal Web de `tpv.py`, clarificar las fronteras/naming del Catálogo, y
construir el Portal Back Office web (greenfield) reutilizando `services/portal` + REST + `services.catalogo`.

*(Informe de solo lectura. No se ha modificado, creado ni eliminado ningún componente.)*
