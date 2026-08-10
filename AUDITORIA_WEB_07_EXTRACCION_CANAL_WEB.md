# AUDITORÍA — FASE WEB-07 · Extracción definitiva del Canal Web del TPV + entrada a Portal Web

**Fecha:** 2026-07-30 · **Tipo:** reorganización exclusivamente arquitectónica (Strangler, incremental,
reversible, compatible, auditada). **Regresiones:** 0 · **Suite:** 701 → **706 passed, 1 skipped**
(701 baseline + 5 tests nuevos WEB-07).

## Objetivo

Extraer FÍSICAMENTE la configuración del Canal Web embebida en `gui/tpv.py` (`_CanalWebConfigDialog`,
antes en las líneas 3657-4166, invocado en 4813) al módulo Canal Web, eliminar el acoplamiento privado
TPV↔Canal Web y sustituir el punto de entrada del TPV por el **Portal Web para empleados** (solo dejar
preparado el punto de entrada; NO desarrollar Portal Web).

## 1 · Código ELIMINADO del TPV

| Elemento | Antes (tpv.py) | Ahora |
|---|---|---|
| `class _CanalWebConfigDialog(QDialog)` (~511 líneas: config del Canal Web — estado, dominios, marca/presencia, conexiones cifradas) | líneas 3657-4167 | **eliminada**; sustituida por un comentario-marcador Strangler que apunta al nuevo hogar |
| Invocación `_CanalWebConfigDialog(parent=self).exec()` en `_GestionPedidosOnlineDialog._configurar` | línea 4813 | **repointada** → abre `PortalWebWindow` |

El TPV ya **no define** la clase de configuración del Canal Web (`hasattr(tpv, "_CanalWebConfigDialog")`
es `False`) y **no importa** `canal_web_config` (verificado por test sobre el código fuente).

## 2 · Código TRASLADADO (nuevo hogar)

| Nuevo fichero | Contenido | Autonomía |
|---|---|---|
| `src/gui/canal_web_config.py` | `CanalWebConfigDialog` (= `_CanalWebConfigDialog` trasladado **verbatim**) + alias de compatibilidad `_CanalWebConfigDialog = CanalWebConfigDialog` (Strangler). Copia las primitivas de estilo que antes tomaba de tpv (`_lbl`/`_btn`/`_ss_tabla_neon`/`_RoundTableCorners` + paleta) | **No importa `gui.tpv`** (verificado por test). Solo consume `services/comercio_digital/*` + `gui.mfa_gui.step_up_sesion` |
| `src/gui/portal_web_gui.py` | `PortalWebWindow` — **placeholder reservado** del Back Office web para empleados. Reutiliza `portal_web.navegacion.SECCIONES` (fuente única). Muestra el mapa de secciones y estado "en preparación" | Autónoma (no importa TPV ni Canal Web) |

## 3 · Dependencias ELIMINADAS / NUEVAS

- **Eliminada:** `catalogo_gestion._abrir_canal_web` importaba `from src.gui.tpv import _CanalWebConfigDialog`
  → ahora `from src.gui.canal_web_config import CanalWebConfigDialog` (Catálogo ya no depende del TPV para
  su redirección "Web").
- **Eliminada:** acoplamiento `tpv → _CanalWebConfigDialog` (config del Canal Web) desaparece.
- **Nueva:** `tpv._GestionPedidosOnlineDialog._configurar → gui.portal_web_gui.PortalWebWindow` (el TPV
  solo NAVEGA a Portal Web).
- **Nueva:** `canal_web_gui.CanalWebWindow._abrir_config → gui.canal_web_config.CanalWebConfigDialog`
  (el módulo Canal Web abre su propia configuración → autosuficiente).
- **Nueva:** `catalogo_gestion → gui.canal_web_config`.
- **Sin cambios:** ningún servicio de backend (`services/comercio_digital/canal_web`, `web_config`/
  `db.web_tienda`, `conexiones`, Hostinger, Marketplace/Integraciones Comerciales) fue tocado — la marca
  sigue teniendo fuente única `web_config` (N7).

## 4 · Dónde aparecía "Canal Web" en el TPV → ahora "Portal Web"

El botón **⚙ Ajustes** del centro de Venta Online (`_GestionPedidosOnlineDialog`) abría la configuración
del Canal Web. Ahora abre **`PortalWebWindow`** (maximizada, ventana propia). La administración de la
presencia digital (marca/dominios/publicación/sincronización/conexiones) se realiza desde el **módulo
Canal Web**: (a) redirección "Web" del **Catálogo** (`_abrir_canal_web`) y (b) asistente **Canal Web**
(`CanalWebWindow` → "⚙ Administrar presencia y configuración de la web").

## 5 · Marketplace / Integraciones / Hostinger — INTACTOS

No se movió, duplicó ni creó ningún conector. `services/marketplace/integraciones_comerciales/`,
`services/comercio_digital/canal_web/proveedores/` (Hostinger) y el catálogo de plataformas quedan como
propietarios únicos. El TPV no importa ninguno.

## 6 · Portal Web — SOLO punto de entrada

`PortalWebWindow` es un **placeholder reservado**: declara las secciones (stock/pedidos/reservas/encargos/
picking/logística web/devoluciones/incidencias…) reutilizando `portal_web.navegacion` y marca el estado
"en preparación". **No se implementó** ninguna pantalla operativa ni lógica de negocio (RESTRICCIÓN
ABSOLUTA de la fase respetada).

## 7 · Pendiente honesto (NO ejecutable en esta fase sin violar la restricción)

`_GestionPedidosOnlineDialog` (rótulo interno "Centro de gestión del CANAL WEB": asistente de creación de
web + dominio + pedidos + Click & Collect + "Ir a la Web") **sigue en el TPV** y aún consume el **servicio**
`comercio_digital.canal_web` (`existe/dominio_activo/crear/buscar_dominios`) para su *state-gate* de
creación. Su migración completa pertenece al **Portal Web para empleados** (pedidos/reservas/Click&Collect)
y al **módulo Canal Web** (creación/dominios); completarla AHORA equivaldría a **desarrollar el Portal Web**,
lo que WEB-07 prohíbe expresamente. Queda como **siguiente fase (WEB-08)**, coherente con el patrón Strangler
ya aplicado (WEB-02/03/04 difirieron explícitamente esta extracción; WEB-07 completa la del *diálogo de
configuración*, el objetivo nombrado en el enunciado).

## 8 · Verificación

- `test_web07_extraccion_canal_web.py` (5): config instancia offscreen + autonomía (no importa tpv);
  TPV sin la clase y sin importar `canal_web_config`, pero abriendo `PortalWebWindow`; `PortalWebWindow`
  instancia offscreen; Catálogo y asistente Canal Web apuntan al módulo extraído.
- **Suite completa:** 706 passed, 1 skipped (0 regresiones sobre 701).
- Compatibilidad: alias `_CanalWebConfigDialog` conservado en el nuevo módulo; `v_id`/rutas/firmas
  públicas de servicios sin cambios.

## Confirmaciones

- [x] TPV abre Portal Web (placeholder). [x] TPV ya no contiene la config del Canal Web.
- [x] Canal Web/Marketplace/Integraciones/Hostinger siguen operando (servicios intactos; config alcanzable
  desde Catálogo y asistente Canal Web). [x] Portal Web abre. [x] 0 regresiones · todos los tests previos
  verdes. [x] Sin secretos en claro · multi-tenant intacto · N7 (sin motores/tablas nuevos).
