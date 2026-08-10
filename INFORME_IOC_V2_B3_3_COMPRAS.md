# IOC v2.0 — BLOQUE III.3 (Parte A): Auditoría previa IOC ↔ Compras

> Auditoría exclusiva (sin cambios de código). Localiza y clasifica los seams de identidad del módulo
> de Compras antes de la adopción progresiva (Strangler) de IOC.

## 1. Superficie de Compras

- **Capa servicio** (`src/services/compras/`): `compras_pro.py` (pedidos recurrentes, órdenes
  abiertas, comparativa proveedores, aprobación), `proveedores_pro.py` (certificaciones, acuerdos
  marco, precios negociados, renovaciones).
- **Capa datos** (`src/db/`): `compras.py`, `proveedores.py`, `pedidos.py`, `reabastecimiento.py`,
  `pagos_proveedor.py`, `devoluciones_baneados.py`.

## 2. Seams de identidad (clasificación)

| Fichero | Capa | Método | Resolución | Riesgo | Dependencias |
|---------|------|--------|-----------|--------|--------------|
| `services/compras/compras_pro.py` | servicio | `_emp` | `fuentes.emp(id_empresa)` | **Bajo** | gemelo.fuentes |
| `services/compras/proveedores_pro.py` | servicio | `_emp` | `fuentes.emp(id_empresa)` | **Bajo** | gemelo.fuentes |
| `db/compras.py` | datos | `_empresa` | `empresa_actual_id()` | Medio (layer) | db.empresa |
| `db/proveedores.py` | datos | `_empresa` | `empresa_actual_id()` | Medio (layer) | db.empresa |
| `db/pedidos.py` | datos | inline | `empresa_actual_id(), tienda_actual_id()` (**emp+tienda**) | Medio (layer) | db.empresa |
| `db/reabastecimiento.py` | datos | `_emp` | `empresa_actual_id()` | Medio (layer) | db.empresa |
| `db/pagos_proveedor.py` | datos | `_emp` | `empresa_actual_id()` | Medio (layer) | db.empresa |

## 3. Otros hallazgos

- **`ref_tienda`, `ref_almacen`, `centros_trabajo`, `codigo_centro`, `id_centro`, UUID IOC:** **0
  usos** en Compras. No hay identidad duplicada ni códigos IOC propios.
- Los accesos SQL de Compras son a **tablas de dominio** (`compras_pedidos*`, `proveedores*`,
  `recepciones*`, `devoluciones*`, `pagos_proveedor*`), no a tablas IOC/Repository.
- Compras resuelve **empresa** (y **tienda** en `pedidos.py`); el almacén es **dato de dominio**
  (`id_almacen` en recepciones/pedidos), no resolución de identidad corporativa.

## 4. Qué se migra ahora y qué permanece

- **Migrables ahora (capa servicio, riesgo bajo, sin invertir capas):**
  `compras_pro._emp`, `proveedores_pro._emp` → adaptador `services/compras/identidad_compras.py`.
- **Permanecen temporalmente (capa datos):** `compras/proveedores/pedidos/reabastecimiento/
  pagos_proveedor`. **Motivo:** ya resuelven con las funciones canónicas `db.empresa` que **IOC
  reutiliza** (misma fuente de verdad, sin divergencia); migrarlas a un adaptador de `services`
  **invertiría** la dependencia `db → services`. Se envolverán en el borde de servicio en una
  iteración posterior.

## 5. Conclusión

Integración quirúrgica y de bajo riesgo, idéntica en forma a Smart Stock (III.2): se enruta el seam de
identidad de la **capa servicio** por `IdentityAPI` (adaptador con empresa/tienda/almacén + contexto),
preservando comportamiento. No se toca ninguna lógica de Compras (pedidos/proveedores/recepciones/
devoluciones/contratos/presupuestos/homologaciones/aprobaciones) ni la GUI.
