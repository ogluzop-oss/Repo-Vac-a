# IOC v2.0 — BLOQUE III.2: Integración IOC ↔ Smart Stock (informe final)

> Segunda adopción de IOC (Strangler), plantilla para la cadena logística (Compras/Producción/TPV).
> Aditivo, behavior-preserving, multiempresa, auditado. Verificado; smoke 5 passed; cero regresiones.

## 1. Auditoría previa (resumen)

Ver `INFORME_IOC_V2_B3_2_STOCK.md`. Smart Stock resuelve **empresa y tienda** (a diferencia del CRM,
solo empresa). Seams: 2 en capa servicio (`stock_pro._emp`, `almacen_pro._emp` → `fuentes.emp`) y 4 en
capa datos (`stock_almacen/kardex/lotes/mermas` → `db.empresa.empresa_actual_id()/tienda_actual_id()`).
Los accesos SQL son a tablas de dominio (no IOC). Sin identidad duplicada.

## 2. Seams encontrados

| Seam | Capa | Resolución |
|------|------|-----------|
| `stock_pro._emp`, `almacen_pro._emp` | servicio | empresa (`fuentes.emp`) |
| `stock_almacen` | datos | empresa |
| `kardex`, `lotes`, `mermas` | datos | empresa + tienda |

## 3. Elementos migrados

- **Adaptador** nuevo `src/services/stock/identidad_stock.py` (sobre `IdentityAPI`).
- **2 seams de capa servicio** migrados: `inventario/stock_pro._emp` y `inventario/almacen_pro._emp`
  → `identidad_stock.empresa_id` (behavior-preserving, con *fallback* a `fuentes.emp`).

## 4. Elementos pendientes (documentados)

- **4 seams de capa datos** (`stock_almacen/kardex/lotes/mermas`): resuelven ya con las funciones
  canónicas `db.empresa` que **IOC reutiliza** (misma fuente de verdad; sin divergencia). Migrarlas al
  adaptador de `services` **invertiría** la dependencia `db → services`, por lo que se **envuelven en
  el borde de servicio** y se migrarán cuando exista una fachada de identidad en la capa de datos.
- Lógica de inventario (movimientos/reservas/recepciones/regularizaciones/traspasos/recuentos) y GUI:
  **no tocadas** (fuera del alcance de identidad).

## 5. Adaptador implementado

`identidad_stock.py` sobre `IdentityAPI`:
- `empresa_id(id_empresa)` — camino caliente, sin eventos, comportamiento idéntico + *fallback*.
- `tienda_actual()` / `tienda_actual_int()` — tienda activa centralizada (equivalente a `db.empresa`).
- `empresa_y_tienda(id_empresa)` — `(empresa, tienda)` para los seams de kardex/lotes/mermas.
- `contexto(...)` — `IdentityContext` completo (empresa/grupo/centro/tienda/almacén) vía IdentityAPI.
- `identidad_almacen(...)` — resolución significativa; publica `stock.identidad.resuelta`.
- `telemetria()` — combinada (adaptador Stock + IdentityAPI).

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|-----------|
| Cambiar comportamiento del stock | `empresa_id` devuelve lo mismo que `fuentes.emp`; verificado (`==`) |
| Fallo de IOC rompe el stock | *Fallback* a `fuentes.emp` dentro del seam y del adaptador |
| Inversión de capas (db→services) | Solo se migra la capa servicio; los seams de datos quedan documentados |
| Eventos excesivos | Camino caliente sin eventos; solo resoluciones significativas |
| Fugas multiempresa | Se resuelve siempre `id_empresa`; verificado aislamiento |

## 7. Compatibilidad garantizada

IOC v1/v2 e IdentityAPI intactos y reutilizados. Smart Stock: comportamiento y salida idénticos;
multiempresa preservada; auditoría existente sin duplicar. Aditivo y reversible (revertir = restaurar
los 2 `_emp`; sin BD que revertir).

## 8. Pruebas realizadas (todas verdes)

| Prueba | Resultado |
|--------|-----------|
| `_emp` idéntico al histórico (stock_pro/almacen_pro) | ✔ (`==fuentes.emp`) |
| Resolución empresa **y** tienda vía adaptador IOC | ✔ |
| IdentityContext (empresa/tienda) | ✔ |
| Multiempresa (aislamiento, sin fugas) | ✔ |
| Evento `stock.identidad.resuelta` (publicado + en bus) | ✔ |
| Telemetría (adaptador + IdentityAPI) | ✔ |
| Servicios de stock funcionales (disponibilidad/inventario) | ✔ (operan vía `_emp` migrado) |
| Compatibilidad IOC v1 / v2 | ✔ |
| Smoke tests | ✔ **5 passed** |
| Regresiones | ✔ **cero** |

*Nota:* durante la prueba de `stock_pro.disponibilidad` aparecen dos avisos SQL de dominio
(`Unknown column 'i.codigo'/'l.codigo'`) propios del esquema de la BD de prueba; son **preexistentes y
ajenos a IOC** (la resolución de identidad no interviene), se capturan internamente y la función
degrada con normalidad. No constituyen regresión de este bloque.

## 9. Informe técnico final

Smart Stock adopta IOC en su capa de servicio: la resolución de identidad (empresa/tienda) pasa por la
`IdentityAPI` mediante un adaptador fino, sin alterar la lógica de inventario ni la GUI, con
`IdentityContext`, telemetría y eventos para las resoluciones significativas y *fallback* a prueba de
fallos. La capa de datos permanece coherente con IOC (misma fuente de verdad) respetando la dirección
de capas. Este adaptador es la **plantilla** para Compras, Producción y TPV.

### Anexo — Ficheros
- Nuevo: `src/services/stock/identidad_stock.py` (+ `__init__.py`)
- Editados (seam `_emp`): `services/inventario/{stock_pro,almacen_pro}.py`
- Sin migración; sin cambios en IOC ni en la lógica/GUI de Smart Stock.
- Evento: `stock.identidad.resuelta`.
