# IOC v2.0 — BLOQUE III.4: Integración IOC ↔ Producción (informe de implementación)

> Cuarta adopción de IOC (Strangler). Aditivo, behavior-preserving, multiempresa, auditado.
> Verificado; smoke 5 passed; cero regresiones. Sin migraciones, sin tablas nuevas.

## 1. Auditoría resumida

Ver `INFORME_IOC_V2_B3_4_PRODUCCION.md`. Los **8 seams de identidad de Producción residen todos en la
capa de servicio** (`src/services/mrp/`). **0** usos de `ref_tienda`/`ref_almacen`/UUID IOC.
`centros_trabajo_prod`/`id_centro` de MRP son **centros productivos (dato de dominio)**, distintos de
los `centros_trabajo` corporativos de IOC → sin identidad duplicada.

## 2. Seams encontrados y 3. Seams migrados

Los 8 (todos migrados, capa servicio):

| Fichero | Forma original | Fallback preservado |
|---------|----------------|---------------------|
| `mrp/produccion_pro.py` | `fuentes.emp` | `fuentes.emp` |
| `mrp/mps.py` | `fuentes.emp` | `fuentes.emp` |
| `mrp/ordenes.py` | `id_empresa or empresa_actual_id()` | `empresa_actual_id` |
| `mrp/centros.py` | `id_empresa or empresa_actual_id()` | `empresa_actual_id` |
| `mrp/bom.py` | `id_empresa or empresa_actual_id()` | `empresa_actual_id` |
| `mrp/costes.py` | `id_empresa or empresa_actual_id()` | `empresa_actual_id` |
| `mrp/planificador.py` | `id_empresa or empresa_actual_id()` | `empresa_actual_id` |
| `mrp/analitica.py` | `id_empresa or empresa_actual_id()` | `empresa_actual_id` |

Cada `_emp` delega ahora en `identidad_produccion.empresa_id(id_empresa)` con el *fallback* idéntico al
original del módulo.

## 4. Seams pendientes

**Ninguno de identidad.** A diferencia de Stock/Compras, Producción no tenía seams de identidad en la
capa de datos: todos estaban en servicios y se han migrado. Queda intacta la lógica de dominio
(órdenes/operaciones/planificación/líneas/estaciones/tiempos/recursos/trazabilidad/consumos) y la GUI.

## 5. Adaptador implementado

`src/services/produccion/identidad_produccion.py` sobre `IdentityAPI` (estructura idéntica a
`identidad_crm/stock/compras`): `empresa_id`, `tienda_actual`, `almacen_actual`,
`empresa_tienda_almacen`, `contexto`, `identidad_orden`, `identidad_maquina`, `identidad_linea`,
`identidad_operacion`, `telemetria`. Con **fallback**, **telemetría** (contadores + snapshot
IdentityAPI) y **eventos** significativos.

## 6. Justificación técnica de cada decisión

- **Migrar los 8 seams (todos de servicio):** al no existir seam de identidad en la capa de datos, la
  migración es completa sin invertir capas (`mrp → produccion(adaptador) → IdentityAPI`).
- **Fallback por módulo:** cada `_emp` conserva su fallback original exacto (`fuentes.emp` o
  `empresa_actual_id`) → comportamiento idéntico garantizado (verificado `==`).
- **`empresa_id` sin eventos:** camino caliente; los eventos se reservan a
  `identidad_orden/operacion/maquina/linea`.
- **No tocar `centros_trabajo_prod`:** son centros productivos (dominio), no identidad IOC.
- **Eventos diferenciados:** `produccion.identidad.orden` y `produccion.identidad.operacion` para
  entidades clave; `produccion.identidad.resuelta` para máquina/línea.

## 7. Compatibilidad

IOC v1/v2, IdentityAPI, CRM (III.1), Stock (III.2) y Compras (III.3) **intactos**. Producción:
comportamiento y salida idénticos; multiempresa preservada; auditoría existente sin duplicar. Aditivo
y reversible (revertir = restaurar los 8 `_emp`; sin BD).

## 8. Resultado de pruebas (todas verdes)

| Prueba | Resultado |
|--------|-----------|
| `_emp` idéntico al histórico (8 módulos) | ✔ |
| Empresa / tienda / almacén | ✔ (trío) |
| IdentityContext | ✔ |
| Aislamiento multiempresa | ✔ |
| Eventos (orden ≥1, operación ≥1, resuelta ≥2) | ✔ |
| Telemetría (adaptador + IdentityAPI) | ✔ |
| Fallback | ✔ |
| Órdenes de producción (`ordenes.listar`) | ✔ |
| Operaciones (`produccion_pro.partes_de_orden`) | ✔ |
| Compatibilidad IOC v1/v2 · CRM · Stock · Compras | ✔ |
| Smoke tests | ✔ **5 passed** |
| Regresiones | ✔ **cero** |

## 9. Informe técnico final

Producción adopta IOC con el patrón validado, siendo la integración **más completa** hasta la fecha:
al residir todos los seams en la capa de servicio, se migran los 8 sin dejar pendientes de identidad,
sin tocar la lógica de fabricación ni la GUI. La cadena **CRM → Stock → Compras → Producción** queda
ya sobre IOC como fuente única de identidad. Próximo objetivo natural: **TPV**.

### Anexo — Ficheros
- Nuevo: `src/services/produccion/identidad_produccion.py` (+ `__init__.py`)
- Editados (seam `_emp`): `services/mrp/{produccion_pro,mps,ordenes,centros,bom,costes,planificador,analitica}.py`
- Sin migración; sin cambios en IOC, lógica de producción ni GUI.
- Eventos: `produccion.identidad.{resuelta,orden,operacion}`.
