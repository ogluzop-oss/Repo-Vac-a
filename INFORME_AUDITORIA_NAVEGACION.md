# Informe de Auditoría de Navegación — Recuperación de Dashboards Enterprise

**Fecha:** 2026-07-06 · **Alcance:** navegación completa del ERP · **Estado:** previo (antes de aplicar cambios).

## 1. Cómo está montada hoy la navegación

El menú (`menu_principal.py → abrir_ventana_por_id`) ya sigue la filosofía **"una tarjeta = ventana-dominio que hospeda sus sub-features como pestañas internas"**. Ejemplos ya en producción:

- **Contabilidad** hospeda *AEAT* como pestaña.
- **Almacenes** / **Mostrar stock** hospedan *Kárdex · Inventario físico · Stock por almacén · Lotes*.
- **Proveedores** hospeda *Compras avanzado*.
- **Tesorería** (8 pestañas), **Aprobaciones** (Workflow·Automatización·Autonomía·Historial), **Seguridad** (Roles·Asignaciones·ACL·Gobierno), **Centro de Inteligencia** (5 pestañas).

Es decir: la arquitectura objetivo **ya existe**; solo falta enganchar los dominios huérfanos a ella.

## 2. Los 9 dashboards Enterprise — estado real

Todos comparten la firma compatible con el menú `(callback_vuelta, usuario, main, parent, **_kw)` y son **autocontenidos** (sus pestañas internas ya SON los submódulos del dominio). Ninguno navega hacia afuera.

| Dashboard | Clase | Contenido interno (submódulos) | Ruta actual |
|---|---|---|---|
| Disaster Recovery | `DRDashboardWindow` | Panel KPIs + acciones (snapshot/drill/runbook) | **ninguna (huérfano)** |
| CRM Comercial | `CRMDashboardWindow` | Leads · Oportunidades · CRM SaaS · KPIs/Forecast | **mal enrutado** (ver §3) |
| MRP / Fabricación | `MRPDashboardWindow` | Órdenes · Sugerencias MRP · KPIs | **ninguna (huérfano)** |
| Calidad | `CalidadDashboardWindow` | Inspecciones · No conformidades · CAPA · Auditorías · KPIs | **ninguna (huérfano)** |
| GMAO / Mantenimiento | `GMAODashboardWindow` | Activos · OT · Planes · KPIs | **ninguna (huérfano)** |
| SAT / Helpdesk | `SATDashboardWindow` | Tickets · KPIs | **ninguna (huérfano)** |
| Finanzas Avanzadas | `FinanzasDashboardWindow` | Ratios/KPIs · Tesorería/Deuda · Riesgo/Crédito · Recomendaciones IA | **ninguna (huérfano)** |
| BI Corporativo | `BICorporativoWindow` | (multiempresa/OLAP/consolidación) | **ninguna (huérfano)** |
| Resiliencia / Offline | `ResilienciaDashboardWindow` | Estado · Circuit breakers · Edge nodes | **ninguna (huérfano)** |

Verificado: `grep` de referencias externas a las 9 clases = **0** en todo `src/` (salvo su propio fichero). No hay accesos, ni directos ni indirectos.

## 3. Rutas a corregir (accesos directos que deberían pasar por su Dashboard)

**Único caso de "acceso directo mal dirigido" encontrado:**
- Tarjeta **"Clientes"** (`v_id="clientes_crm"`) → hoy abre `clientes_gui` (gestión de clientes) directamente, existiendo `CRMDashboardWindow` como pantalla-dominio. Debe abrir el **Dashboard Comercial** primero y desde él accederse a la gestión de clientes.

**El resto de tarjetas ya están bien** (abren su hub de dominio) o son módulos operativos **sin** Dashboard Enterprise asociado (Logística, Ventas, Stock, Mermas, Etiquetas, etc.), por lo que su ruta directa es correcta.

## 4. Los 8 dashboards huérfanos NO tienen tarjeta ni dominio-anfitrión

Aquí está la decisión arquitectónica: hay 8 dominios completos sin ninguna puerta de entrada. Se agrupan en tres situaciones:

- **BI Corporativo** → su sitio natural es el **Centro de Inteligencia** (lo indicaste explícitamente): se añade como pestaña del hub existente.
- **Finanzas Avanzadas** → familia financiera; encaja como pestaña dentro de **Tesorería** (o Contabilidad), completando esa rama sin tocarla.
- **MRP · Calidad · GMAO · SAT · DR · Resiliencia** → son 6 dominios **nuevos** sin ninguna tarjeta ni ventana previa donde hospedarse. Para respetar "cada dominio = una puerta de entrada coherente" necesitan **presencia de menú propia** que abra su Dashboard Enterprise (que ya contiene todo el dominio en pestañas).

## 5. Mapeo definitivo (por afinidad funcional — decisión del usuario: sin tarjetas nuevas, cada dominio donde se espera, convertir ventana a anfitriona si hace falta)

| Dashboard | Dominio de usuario | Ubicación (ventana existente, reutilizando su acceso) |
|---|---|---|
| CRM Comercial | Clientes / Comercial | Tarjeta **"Clientes"** → se convierte en hub CRM; el **Dashboard Comercial es la 1ª pestaña (entrada)**, luego *Clientes* (`clientes_gui`) y *SAT* |
| SAT / Helpdesk | Servicio postventa (cliente) | pestaña dentro del hub **Clientes/CRM** (postventa) |
| Calidad | Calidad de suministro/recepción | pestaña en **Proveedores/Compras** (junto a homologación de proveedores) |
| MRP / Fabricación | Planificación de material / producción | pestaña en **Almacenes** (operaciones físicas / reposición) |
| GMAO / Mantenimiento | Mantenimiento de activos | pestaña en **Almacenes** (activos/instalaciones) |
| Finanzas Avanzadas | Financiero | pestaña en **Tesorería** |
| DR + Resiliencia | Infra / continuidad | pestañas en **Seguridad** |
| BI Corporativo | Inteligencia | pestaña en **Centro de Inteligencia** |

**Criterio:** afinidad funcional real (no un vertedero técnico). Clientes/CRM agrupa lo orientado al cliente (comercial + gestión + postventa); Compras agrupa calidad de suministro; Almacenes agrupa operaciones físicas (producción/reposición + mantenimiento de activos); Tesorería agrupa lo financiero; Seguridad agrupa infra/continuidad; Centro de Inteligencia agrupa analítica corporativa. Tesorería/Seguridad/Centro de Inteligencia ya son tab-based (integración aditiva); Clientes/Compras/Almacenes se **convierten** en anfitrionas con pestañas (permitido explícitamente), reutilizando su tarjeta y contenido actual como primera pestaña.

## 6. Garantías

- Cero código nuevo de negocio; se reutilizan las ventanas tal cual (misma clase, misma firma).
- Sin duplicar ventanas ni crear dashboards alternativos.
- No se tocan SOMA, Mission Engine, Workflow, Gobierno, Autonomía ni la arquitectura del Plan UI Enterprise (añadir una pestaña a un hub existente es completar el hub, no reescribirlo).

## 6.bis RESULTADO APLICADO (recuperación de dashboards — COMPLETADA)

Los 9 dashboards, antes huérfanos (0 referencias), quedan integrados reutilizando las ventanas
existentes (misma clase/firma, sin duplicar, sin tarjetas nuevas):

| Dashboard | Integración realizada |
|---|---|
| CRM Comercial | Tarjeta **"Clientes"** re-enrutada → `CRMDashboardWindow` (entrada del dominio). Añadidas pestañas *Clientes* (`clientes_gui`) y *SAT/Postventa*. |
| SAT / Helpdesk | Pestaña dentro del hub CRM. |
| Calidad | Nueva sección **"Calidad"** en Compras/Proveedores (patrón sidebar+stack existente). |
| MRP / Fabricación | Pestaña en **Almacenes** (convertida a anfitriona con pestañas). |
| GMAO / Mantenimiento | Pestaña en **Almacenes**. |
| Finanzas Avanzadas | Pestaña en **Tesorería**. |
| DR + Resiliencia | Pestañas en **Seguridad**. |
| BI Corporativo | Pestaña (lazy) en **Centro de Inteligencia**. |

**Verificado:** AST OK · las 9 clases pasan de 0 → 1 referencia (ninguna huérfana) · todas las
ventanas anfitrionas construyen sin error offscreen · `tesoreria` maximiza · smoke `5 passed` ·
sin tarjetas nuevas · SOMA y Plan UI Enterprise intactos.

## 7. Bloque pendiente tras dashboards (fases posteriores de este mismo prompt)

TPV (báscula/devoluciones/autocobro) · Responsive P2 (6 pantallas) · Jobs Enterprise (registro selectivo) · Combo global (overrides inline) · MFA (cableado login) · Comunicaciones (auditoría) · Fiscalidad (documentación) · Multitenant (revisión no-rotura). Se abordan después de cerrar la recuperación de dashboards.
