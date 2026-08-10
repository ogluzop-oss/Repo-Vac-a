# IOC v2.0 — BLOQUE III.2: Auditoría previa de integración IOC ↔ Smart Stock

> Auditoría exclusiva (sin cambios de código). Localiza los seams de identidad del módulo de stock
> antes de la adopción progresiva (Strangler) del motor IOC.

## 1. Superficie de Smart Stock

- **Capa servicio** (`src/services/inventario/`): `stock_pro.py` (stock comprometido/futuro/
  disponibilidad, conteo cíclico, reubicación), `almacen_pro.py` (zonas, picking/packing,
  cross-docking, consolidación).
- **Capa datos** (`src/db/`): `stock_almacen.py`, `kardex.py`, `lotes.py`, `mermas.py`, `stock.py`,
  `inventario_fisico.py` — movimientos, inventarios, reservas, recepciones, regularizaciones,
  traspasos, recuentos, ubicaciones.

## 2. Seams de identidad detectados

| Fichero | Capa | Resolución actual |
|---------|------|-------------------|
| `services/inventario/stock_pro.py` | servicio | `_emp` → `fuentes.emp(id_empresa)` (empresa) |
| `services/inventario/almacen_pro.py` | servicio | `_emp` → `fuentes.emp(id_empresa)` (empresa) |
| `db/stock_almacen.py` | datos | `id_empresa or empresa_actual_id()` (empresa) |
| `db/kardex.py` | datos | `empresa_actual_id(), tienda_actual_id()` (**empresa + tienda**) |
| `db/lotes.py` | datos | `id_empresa or empresa_actual_id()` + `tienda_actual_id()` |
| `db/mermas.py` | datos | `empresa_actual_id(), tienda_actual_id_int()` (**empresa + tienda**) |

**Diferencia con CRM:** Smart Stock resuelve **empresa Y tienda** (no solo empresa).

## 3. Accesos directos / duplicidades

- Los accesos SQL de Smart Stock son a **tablas de dominio** (`stock_tienda`, `stock_almacen`,
  `movimientos_stock`, `lotes*`, `mermas*`, `ubicaciones`), **no** a tablas IOC/Repository.
- **No hay identidad duplicada**: todos los seams resuelven `id_empresa`/`id_tienda` mediante las
  funciones canónicas `db.empresa.empresa_actual_id()` / `tienda_actual_id()` — que son **exactamente
  las que IOC (`_base.emp`) reutiliza**. No existen ids de identidad paralelos ni códigos propios.
- El uso de `id_almacen`/`codigo_almacen` es **dato de dominio** (qué almacén), no resolución de
  identidad corporativa.

## 4. Clasificación de los seams (para Strangler layer-safe)

- **Migrables ahora (capa servicio):** `stock_pro._emp`, `almacen_pro._emp` → adaptador
  `services/stock/identidad_stock.py` (services→services, sin invertir capas).
- **Pendientes (capa datos):** `stock_almacen/kardex/lotes/mermas`. Ya resuelven vía las funciones
  canónicas `db.empresa` que IOC reutiliza (misma fuente de verdad, sin divergencia). Migrarlas a un
  adaptador de `services` **invertiría** la dependencia `db → services`; por tanto se **envuelven en
  el borde de servicio** y se migrarán cuando exista una fachada de identidad en la capa de datos.

## 5. Conclusión

Integración de riesgo bajo y quirúrgica: el seam de identidad de la **capa servicio** de Smart Stock
se enruta por `IdentityAPI` (adaptador), preservando comportamiento (empresa **y** tienda disponibles
vía `IdentityContext`). La capa de datos ya es coherente con IOC (misma fuente de verdad) y se respeta
la dirección de capas. No se toca ninguna lógica de inventario ni la GUI.
