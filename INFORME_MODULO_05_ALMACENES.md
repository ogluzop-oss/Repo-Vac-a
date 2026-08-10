# Informe Técnico — Módulo 5: Almacenes

**Auditoría (ya existía):** ubicaciones con pasillo/estantería/balda/nivel (tienda y almacén),
mapa (mapa_x/y, real_x/y), almacenes (tipo/estado) — `ubicaciones`, `almacen`, `stock_almacen`.

**Gaps implementados (migr 0105 + `src/services/inventario/almacen_pro.py`):**
- **zonas · capacidad · restricciones**: columnas `ubicaciones.zona/capacidad/restriccion` +
  `set_atributos_ubicacion` · `ubicaciones_por_zona`.
- **picking / packing**: `almacen_picking(_lineas)` + `crear_picking` (resuelve ubicación desde
  `ubicaciones`), `confirmar_linea_picking`, `cerrar_packing`, `listar_picking`.
- **cross-docking**: `cross_docking_desde_recepcion` (picking marcado → `LISTO_EXPEDIR` al empaquetar).
- **consolidación**: `consolidar_pickings` (une varias listas en una).

**Reutilización:** `ubicaciones` (pasillo/estantería/nivel/mapa existentes) para resolver ubicación de
picking; pedidos/recepciones como origen. Auditoría en cada operación; multiempresa.

**Pruebas:** migr 0105; picking creado + listado; cross-docking → packing `LISTO_EXPEDIR`;
consolidación de 2 listas. **smoke 5 passed.**

**Mejoras futuras:** rutas internas de picking optimizadas por ubicación (reutilizar el optimizador
haversine del M1/rutas adaptado a coordenadas de almacén); control de capacidad al ubicar; GUI en
Almacenes.
