# AUDITORÍA — FASE WEB-08 · `_GestionPedidosOnlineDialog` (TPV) → `PortalWebHome` (Portal Web)

**Fecha:** 2026-07-30 · **Tipo:** migración exclusivamente arquitectónica (Strangler; sin desarrollar
funcionalidades, sin reescribir, sin cambiar lógica). **Regresiones:** 0 · **Suite:** 706 → **710 passed,
1 skipped** (+4 tests WEB-08).

## Objetivo

Sacar del TPV el componente `_GestionPedidosOnlineDialog` ("Centro de gestión de pedidos online / Canal
Web") y convertirlo en el **núcleo del Portal Web para empleados** (`PortalWebHome`), dejando el TPV como
mero *router* hacia `PortalWebWindow` y preparando la navegación estructural del Portal Web.

## 1 · Código EXTRAÍDO del TPV

| Elemento | Antes (tpv.py) | Ahora |
|---|---|---|
| `class _GestionPedidosOnlineDialog(QDialog)` — ~842 líneas (asistente de creación de web + panel operativo de pedidos/Click&Collect + dominio + sincronización + "Ir a la Web") | líneas 3665-4506 | **eliminada**; sustituida por comentario-marcador Strangler |
| Invocación en `SmartManagerTPV._abrir_gestion_pedidos_online` (tarjeta "🌐 Venta online") | instanciaba `_GestionPedidosOnlineDialog(...).exec()` | **repointada** → abre `PortalWebWindow` (router) |

Verificado: `hasattr(tpv, "_GestionPedidosOnlineDialog") == False` y `hasattr(tpv, "PortalWebHome") == False`.

## 2 · Código TRASLADADO al Portal Web

| Fichero | Contenido |
|---|---|
| `src/gui/portal_web_home.py` (**nuevo**) | `class PortalWebHome(QDialog)` = el componente extraído **verbatim** (misma lógica, mismos servicios, mismas validaciones). Alias de compatibilidad `_GestionPedidosOnlineDialog = PortalWebHome`. Es el **núcleo/pantalla inicial** del Portal Web. |
| `src/gui/_neon_ui.py` (**nuevo**) | Primitivas de estilo compartidas (`_lbl/_btn/_card/_sep/_ss_tabla_neon/_RoundTableCorners` + paleta) copiadas de tpv.py para que los módulos extraídos NO importen `gui.tpv`. |
| `src/gui/portal_web_gui.py` (**ampliado**) | `PortalWebWindow` pasa de *placeholder* (WEB-07) a **shell de navegación**: barra lateral de 8 secciones (Inicio · Pedidos Online · Reservas · Encargos · Stock · Logística · Clientes · Configuración) + área de contenido con `PortalWebHome` como pantalla inicial; secciones reservadas → marcador "en preparación". |

## 3 · Dependencias ELIMINADAS

- `tpv → _GestionPedidosOnlineDialog` (el TPV ya no contiene ni instancia lógica del Portal Web).
- El TPV **no importa** `portal_web_home` ni referencia `PortalWebHome` (solo comentarios).

## 4 · Dependencias NUEVAS

- `tpv._abrir_gestion_pedidos_online → gui.portal_web_gui.PortalWebWindow` (**router**, import perezoso).
- `portal_web_gui.PortalWebWindow → gui.portal_web_home.PortalWebHome` (import perezoso al construir el home).
- `portal_web_home → gui._neon_ui` (helpers de estilo, a nivel de módulo).
- `portal_web_home → gui.tpv._CobroDialog/_EnvioDialog/_VentaOnlineDialog` (**imports PEREZOSOS** en el
  punto de uso): reutilización de diálogos de POS que **siguen en el TPV** (Objetivo 5, no se duplican ni
  se mueven). `portal_web_home` **NO** importa `gui.tpv` a nivel de módulo → sin ciclo de importación.
- `portal_web_home._configurar → gui.canal_web_config.CanalWebConfigDialog` (Ajustes reutiliza Canal Web).

## 5 · Reutilización (Objetivo 5) — el Portal Web NO implementa lógica propia

`PortalWebHome` conserva sus llamadas a servicios existentes: `services/tpv/online_orders_service`
(pedidos/estados/envío), `services/comercio_digital/canal_web` (existe/dominio/crear/publicar/sincronizar),
pasarela de pagos, y reutiliza los diálogos POS del TPV (`_CobroDialog`/`_EnvioDialog`/`_VentaOnlineDialog`)
y la configuración de Canal Web. No se creó backend/tablas/motores nuevos (N7).

## 6 · Navegación futura PREPARADA (Objetivo 4/6) — sin desarrollar

`PortalWebWindow` deja lista la estructura para WEB-09..WEB-12: las secciones Reservas/Encargos/Stock/
Logística/Clientes/Configuración existen en la barra lateral y muestran "en preparación". No se implementó
pedidos online/reservas/click&collect/stock web/logística web (RESTRICCIÓN ABSOLUTA respetada).

## 7 · Desacoplamiento TPV ↔ Portal Web (Objetivo 7)

El TPV queda reducido a **router → PortalWebWindow**. No conoce la implementación interna, no importa clases
privadas del Portal Web, no contiene su lógica. La única relación restante es Portal Web → TPV para
**reutilizar** tres diálogos de POS (import perezoso), reutilización legítima (Objetivo 5), no acoplamiento
de control.

## 8 · No modificado (Objetivo 8)

Marketplace · Canal Web (servicios) · Portal Cliente · Catálogo · Stock · Caja · RRHH · Facturación ·
Pedidos · AWS · Terraform · Docker · Entitlements: **intactos**. (Se creó `_neon_ui.py` y se amplió
`portal_web_gui.py`, ambos del área Portal Web; los diálogos POS del TPV no se tocaron.)

## 9 · Verificación / pruebas

- `test_web08_portal_web_home.py` (4): núcleo extraído instancia offscreen (asistente + operativo) + alias;
  `portal_web_home` no importa tpv a nivel de módulo; TPV sin la clase y solo abriendo PortalWebWindow;
  shell de navegación de 8 secciones con el núcleo como pantalla inicial y marcador en las reservadas.
- `test_web07_extraccion_canal_web.py` (5) sigue verde.
- **Suite completa:** 710 passed, 1 skipped (0 regresiones sobre 706).

## Confirmaciones (Objetivo 9)

- [x] TPV abre correctamente el Portal Web (router). [x] El Portal Web abre correctamente (shell + núcleo).
- [x] `_GestionPedidosOnlineDialog` ya no existe dentro del TPV (alias conservado en el nuevo módulo).
- [x] No hay importaciones privadas TPV → Portal Web (solo router; Portal Web → TPV es reutilización POS
  perezosa). [x] Marketplace / Canal Web / Portal Cliente siguen funcionando. [x] Todos los tests previos
  verdes · 0 regresiones. [x] N7 · multi-tenant intacto · sin secretos · navegación futura preparada.
