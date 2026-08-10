# Módulos por edición de Smart Manager

Referencia de qué módulos y funciones están disponibles en cada **edición** (tipo de comercio). La edición se
fija por instalación (`SMART_MANAGER_EDITION` → onboarding → por defecto `SUPERMARKET`) y la resuelve el motor
único `src/services/verticales.py`.

> **Regla permanente:** ningún módulo se **elimina** por edición. Se **gatea** (se oculta la tarjeta o se
> sustituye la función), conservando el código para todas las ediciones. Cambiar la disponibilidad = editar
> una línea de la matriz `_REGLAS` en `verticales.py`.

Leyenda: **✅** disponible · **—** oculto · **↷** sustituido por otra función.

Las 5 ediciones: **🛒 Supermarket · 🏬 Retail · 💊 Pharmacy · 👕 Textil · 🥖 Bakery & Coffee**.

---

## A) Módulos COMUNES a las 5 ediciones

Disponibles en todas las ediciones (sujetos solo a *rol*, no a edición):

| Módulo | Función |
|---|---|
| **TPV** | Punto de venta y cobro (efectivo/tarjeta/mixto), tickets, devoluciones |
| **Logística** | Recepción de palés, albaranes y expediciones |
| **Stock** | Existencias y kárdex (mostrar stock) |
| **Ubicación** | Mapa de ubicación en tienda (dónde está cada producto) |
| **Artículo** | Alta/ficha de artículos y búsqueda |
| **Documentos** | Centro documental (PDFs, albaranes, facturas, tickets de operación) |
| **Correo** | Correo corporativo + circulares/encuestas internas |
| **Mermas** | Registro de pérdidas/roturas |
| **Etiquetas** | Etiquetas de precio y códigos de barras |
| **Reposición** | Informe de reposición + previsión de demanda (IA) |
| **Ventas** | Analítica de ventas y márgenes |
| **Gestión Caja** | Abrir/cerrar caja y caja fuerte, cierre diario, transferir efectivo |
| **Proveedores** | Compras, proveedores, aprovisionamiento, calidad (pestaña) |
| **Clientes (CRM)** | Clientes, oportunidades, fidelización, soporte SAT (pestaña) |
| **Contabilidad** | Asientos, diario/mayor, IVA y modelos AEAT/fiscal (pestaña) |
| **Tesorería** | Cuentas, cashflow, conciliación, SEPA, banca PSD2 |
| **Centro de Inteligencia (BI)** | Dashboards, gemelo digital, predicción, simulador |
| **Seguridad** | Roles/permisos (RBAC), gobierno, MFA |
| **Aprobaciones** | Flujos de aprobación, automatización, historial |
| **Suscripción (SaaS)** | Plan, consumo y facturación de la suscripción |
| **RRHH** | Empleados, nóminas, fichajes, expedientes |
| **Proyectos** | Kanban/Gantt + rentabilidad |
| **Portal del empleado** | Autoservicio del empleado |
| **Almacenes** | Kárdex, inventario físico, stock por almacén, lotes, slotting/rutas, GMAO (y **MRP** salvo Pharmacy/Bakery) |
| **Cámaras** | Videovigilancia 24/7 |
| **Migrar datos** | Importador maestro (onboarding de BD) |
| **App Store** | Marketplace de plugins/extensiones |
| **Cloud Manager** | Panel multi-tenant (*solo SUPERADMIN*) |

---

## B) Módulos/tarjetas específicos de edición

| Módulo (tarjeta) | SUP | RET | PHA | TEX | BAK | Función |
|---|:--:|:--:|:--:|:--:|:--:|---|
| **Catálogo Web** | ✅ | ✅ | ✅ | ✅ | — | Presencia digital (Canal Web). En Bakery se usa carta física en el local |
| **Reparto** | ✅ | ✅ | ✅ | ✅ | — | Flota + rutas de reparto (la entrega descuenta stock) |
| **Distribución (B2B)** | ✅ | ✅ | — | ✅ | — | Venta mayorista: pedido cliente → picking → expedición |
| **Recetas** | — | — | ✅ | — | — | Recetas y dispensación (descuenta stock) |
| **Obrador** | — | — | — | — | ✅ | Producción diaria de panadería (consume BOM + alta de vendibles) |

---

## C) Funciones internas de módulos (activadas/ocultas/sustituidas por edición)

| Función (dentro de un módulo) | SUP | RET | PHA | TEX | BAK |
|---|:--:|:--:|:--:|:--:|:--:|
| **TPV · Báscula** (venta a granel por peso) | ✅ | — | — | ↷ variantes | — |
| **TPV · Autocobro** (self-checkout) | ✅ | — | — | — | — |
| **TPV · Venta almacén** (pedidos online al central) | ✅ | ✅ | ✅ | ✅ | — |
| **TPV · Tarjeta regalo** | ✅ | ✅ | ✅ | ✅ | — |
| **TPV · Devolución** | ✅ | ✅ | ✅ | ✅ | — |
| **Productos · A granel** | ✅ | — | — | — | — |
| **Productos · Variantes talla/color** | ✅ | ✅ | — | ✅ | — |
| **Productos · Lotes y caducidad** | ✅ | ✅ | ✅ | — | ✅ |
| **Almacenes · MRP/Fabricación** | ✅ | ✅ | — | ✅ | ↷ Obrador |

---

## D) Resumen por edición

**🛒 Supermarket** — la más completa. Añade Reparto y Distribución B2B. TPV con **báscula**, **autocobro** y
**granel**; **variantes** y **lotes** activos; **MRP** disponible; Catálogo Web activo.

**🏬 Retail** — tienda general. Reparto y Distribución B2B. TPV **sin báscula/autocobro/granel**; **variantes**
y **lotes** activos; **MRP** y Catálogo Web disponibles.

**💊 Pharmacy** — farmacia/parafarmacia. Añade **Recetas** y Reparto (sin Distribución B2B).
Sin báscula/granel/variantes; **lotes/caducidad** clave; **MRP oculto**; Catálogo Web activo.

**👕 Textil** — moda y calzado. Reparto y Distribución B2B. TPV **báscula → variantes talla/color**; granel y
lotes ocultos; **MRP** y Catálogo Web disponibles.

**🥖 Bakery & Coffee** — panadería/cafetería. Añade **Obrador**. **Sin** báscula/granel (venta por unidad),
**sin** Catálogo Web, **sin** Reparto, **sin** Distribución B2B. TPV **simplificado** (ver sección E).
**MRP → Obrador**.

---

## E) TPV de la edición Bakery (venta rápida por unidad)

Ajustes propios para hacer el TPV de panadería intuitivo:

- **Sin báscula/granel**: se vende por **unidad**. En el hueco de la báscula aparece el botón **🧁 Productos**,
  que abre una **rejilla de botones grandes** agrupados en 3 familias: **Dulce · Salado · Bebidas**
  (`_RejillaProductosBakery`, reutiliza `db/familias` + el alta de línea del TPV). Las familias por defecto de
  la edición Bakery son exactamente `["Dulce", "Salado", "Bebidas"]`.
- **Sin Devolución** ni **Venta almacén** (pedidos online) en Acciones avanzadas.
- **Sin Tarjeta regalo** en el panel de acciones.
- **Sin Catálogo Web** (carta física en el local).

---

*Fuente de verdad: `src/services/verticales.py` (`FUNCIONES` + `_REGLAS`). Este documento es un reflejo legible
de esa matriz; ante cualquier duda, manda el código.*
