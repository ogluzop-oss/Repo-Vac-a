# Informe Técnico — Módulo 2: Proveedores (Enriquecimiento funcional)

**Metodología:** auditoría → informe → implementar solo lo que falta → pruebas → verificación.
Aditivo/reversible; sin duplicar; SOMA/UI Enterprise/navegación intactos.

## 1. Auditoría — qué existía ya (NO tocado)

| Propuesta | Estado | Dónde |
|---|---|---|
| homologaciones | ✅ | `db/proveedores` (homologar, esta_homologado, `homologacion_estado`, bloquear) |
| evaluaciones · scoring · incidencias | ✅ | tabla `proveedores_evaluacion` (cumplimiento_plazo, calidad, incidencias, rechazos, devoluciones, `valoracion_global`) |
| históricos | ✅ | `proveedores_evaluacion` (periodo/fecha) |
| auditorías | ✅ | `log_auditoria` en las operaciones de compras/proveedores |
| documentación | ✅ | Centro Documental (ref_documento) |

## 2. Diferencias — qué faltaba (implementado)

| Propuesta | Estado | Acción |
|---|---|---|
| certificaciones | ❌ | **nuevo** `proveedor_certificaciones` + API |
| contratos / acuerdos marco | ❌ | **nuevo** `proveedor_acuerdos_marco` + API |
| precios negociados | ❌ | **nuevo** `proveedor_precios_negociados` + API (precio vigente por artículo) |
| renovaciones automáticas | ❌ | **nuevo** job Scheduler `proveedores_renovaciones` (alerta + renueva) |

## 3. Funcionalidades reutilizadas (no duplicadas)

- **Renovaciones** reutilizan el **Scheduler** (job `proveedores_renovaciones`, registrado en el
  JobRegistry → visible/configurable en la pestaña "Programador") y el sistema de **notificaciones**
  (`notificaciones.emitir`) para avisar de vencimientos a ADMINISTRADOR/GERENTE.
- **Precios negociados** se integran con el catálogo de artículos existente (`codigo_articulo`) y con
  los acuerdos marco (`id_acuerdo`); `precio_vigente()` es reutilizable desde Compras/pedidos.
- **Auditoría** (`log_auditoria`) en cada alta/cambio. Multiempresa por `id_empresa`.
- Homologación/evaluación/scoring **no se han tocado** (ya existían).

## 4. Funcionalidades nuevas (resumen técnico)

- migr **0103**: `proveedor_certificaciones`, `proveedor_acuerdos_marco`, `proveedor_precios_negociados`.
- `src/services/compras/proveedores_pro.py`:
  - certificaciones: `añadir_certificacion` · `certificaciones`.
  - acuerdos marco: `crear_acuerdo_marco` · `acuerdos_marco`.
  - precios negociados: `set_precio_negociado` · `precio_vigente`.
  - renovaciones: `vencimientos(dias)` · `_job_renovaciones` (alerta + renueva `renovacion_auto`
    extendiendo `meses_renovacion`) · `registrar_jobs_proveedores`.
- Catálogo de jobs: alta de `proveedores_renovaciones` (categoría compras, 24 h, permiso `compras.ver`).

## 5. Pruebas realizadas y superadas

migr 0103 aplicada. Certificación + acuerdo marco + precio negociado creados; `precio_vigente` devuelve
el precio vigente; `vencimientos(30)` detecta 1 certificación + 1 acuerdo; el job alerta y **renueva**
el acuerdo con `renovacion_auto`; el job aparece en el catálogo del Scheduler. **smoke 5 passed.**

## 6. Posibles mejoras futuras

- Superficie GUI dedicada dentro de la sección **Proveedores** de Compras (hoy los datos se gestionan
  por servicios + el job de renovaciones; la sección Proveedores puede listar certificaciones/acuerdos/
  precios reutilizando su patrón sidebar+stack).
- Aplicar `precio_vigente()` automáticamente al crear líneas de pedido de compra.
- Adjuntar el documento de la certificación al Centro Documental con caducidad sincronizada.
