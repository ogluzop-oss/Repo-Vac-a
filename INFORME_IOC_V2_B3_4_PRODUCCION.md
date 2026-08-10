# IOC v2.0 — BLOQUE III.4 (Parte A): Auditoría previa IOC ↔ Producción

> Auditoría exclusiva (sin cambios de código). Localiza y clasifica los seams de identidad del módulo
> de Producción (MRP/Fabricación) antes de la adopción progresiva (Strangler) de IOC.

## 1. Superficie de Producción

Servicios `src/services/mrp/`: `produccion_pro` (partes de trabajo, CRP), `mps` (plan maestro),
`ordenes` (órdenes de fabricación), `centros` (centros de trabajo productivos + capacidad/rutas),
`bom`, `costes`, `planificador` (explosión MRP), `analitica`.

## 2. Seams de identidad (clasificación)

| Fichero | Método | Capa | Resolución | Riesgo | Migrable |
|---------|--------|------|-----------|--------|----------|
| `mrp/produccion_pro.py` | `_emp` | servicio | `fuentes.emp` | Bajo | **Sí** |
| `mrp/mps.py` | `_emp` | servicio | `fuentes.emp` | Bajo | **Sí** |
| `mrp/ordenes.py` | `_emp` | servicio | `id_empresa or empresa_actual_id()` | Bajo | **Sí** |
| `mrp/centros.py` | `_emp` | servicio | `id_empresa or empresa_actual_id()` | Bajo | **Sí** |
| `mrp/bom.py` | `_emp` | servicio | `id_empresa or empresa_actual_id()` | Bajo | **Sí** |
| `mrp/costes.py` | `_emp` | servicio | `id_empresa or empresa_actual_id()` | Bajo | **Sí** |
| `mrp/planificador.py` | `_emp` | servicio | `id_empresa or empresa_actual_id()` | Bajo | **Sí** |
| `mrp/analitica.py` | `_emp` | servicio | `id_empresa or empresa_actual_id()` | Bajo | **Sí** |

**Diferencia con Stock/Compras:** los 8 seams están **todos en la capa de servicio** → todos
migrables ahora sin invertir capas (no hay seam de capa datos que dejar pendiente).

## 3. Otros hallazgos

- **`ref_tienda`, `ref_almacen`, UUID/códigos IOC:** **0 usos**. No hay identidad corporativa
  duplicada.
- **`centros_trabajo_prod` / `id_centro` de MRP** = **centros de trabajo PRODUCTIVOS (dato de
  dominio)**, explícitamente distintos de los `centros_trabajo` corporativos de IOC (así lo indica el
  propio docstring de `mrp/centros.py`). No se tocan: son datos de fabricación, no identidad.
- `ordenes.py` resuelve también `tienda_actual_id` (contexto de tienda); es dato de contexto, no
  identidad corporativa duplicada.
- Los accesos SQL son a tablas de dominio (`ordenes_fabricacion`, `centros_trabajo_prod`,
  `capacidades_prod`, `bom*`, `partes_trabajo_prod`, `mrp_plan_maestro`), no a IOC/Repository.

## 4. Qué se migra ahora / qué permanece

- **Migrables ahora (los 8 `_emp` de capa servicio):** delegar en
  `identidad_produccion.empresa_id()` con *fallback* idéntico al original de cada módulo.
- **Permanece intacto:** toda la lógica de fabricación (órdenes/operaciones/planificación/líneas/
  estaciones/tiempos/recursos/trazabilidad/consumos), las consultas SQL de dominio, los centros
  productivos y la GUI.

## 5. Conclusión

Integración de bajo riesgo y **más completa** que en Stock/Compras: al residir todos los seams en la
capa de servicio, se migran los 8 al adaptador `IdentityAPI`, preservando comportamiento (empresa/
tienda/almacén vía `IdentityContext`), sin tocar ninguna lógica de producción ni la GUI.
