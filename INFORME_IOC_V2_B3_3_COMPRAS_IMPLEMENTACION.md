# IOC v2.0 — BLOQUE III.3: Integración IOC ↔ Compras (informe de implementación)

> Tercera adopción de IOC (Strangler). Aditivo, behavior-preserving, multiempresa, auditado.
> Verificado; smoke 5 passed; cero regresiones. Sin migraciones, sin tablas nuevas.

## 1. Auditoría previa (resumen)

Ver `INFORME_IOC_V2_B3_3_COMPRAS.md`. Compras resuelve **empresa** (y **tienda** en `pedidos.py`);
el almacén es dato de dominio. **0** usos de `ref_tienda`/`ref_almacen`/`centros_trabajo`/UUID IOC →
sin identidad duplicada. Seams: 2 en capa servicio (`compras_pro`, `proveedores_pro` → `fuentes.emp`)
y 5 en capa datos (`compras/proveedores/pedidos/reabastecimiento/pagos_proveedor`).

## 2. Seams migrados

| Seam | Capa | Antes → Después |
|------|------|-----------------|
| `services/compras/compras_pro._emp` | servicio | `fuentes.emp` → `identidad_compras.empresa_id` (fallback `fuentes.emp`) |
| `services/compras/proveedores_pro._emp` | servicio | `fuentes.emp` → `identidad_compras.empresa_id` (fallback `fuentes.emp`) |

## 3. Seams pendientes (documentados)

`db/compras.py`, `db/proveedores.py`, `db/pedidos.py`, `db/reabastecimiento.py`,
`db/pagos_proveedor.py` (capa datos). **Justificación:** ya resuelven con las funciones canónicas
`db.empresa` que IOC reutiliza (misma fuente de verdad); migrarlas invertiría `db → services`. Se
envolverán en el borde de servicio en una iteración posterior. Lógica de Compras (pedidos/proveedores/
recepciones/devoluciones/contratos/presupuestos/homologaciones/aprobaciones) y GUI: **no tocadas**.

## 4. Adaptador implementado

`src/services/compras/identidad_compras.py` sobre `IdentityAPI`:
`empresa_id`, `tienda_actual`, `almacen_actual`, `empresa_tienda_almacen`, `contexto`,
`identidad_proveedor`, `identidad_pedido`, `telemetria`. Incorpora **fallback** (a `fuentes.emp`),
**telemetría** (contadores + snapshot IdentityAPI) y **eventos** (`compras.identidad.resuelta`) solo
en resoluciones significativas (nunca en el camino caliente).

## 5. Justificación arquitectónica de cada decisión

- **Migrar solo capa servicio:** respeta la dirección `Compras → IdentityAPI → … → IOC` sin invertir
  `db → services`. Bajo riesgo, alto valor (los `_pro` son el punto de entrada moderno de Compras).
- **`empresa_id` sin eventos:** es camino caliente (cada operación resuelve empresa); publicar
  eventos ahí saturaría el bus. Los eventos se reservan a `identidad_proveedor/identidad_pedido`.
- **Fallback a `fuentes.emp`:** garantiza comportamiento idéntico incluso si IOC fallara → cero
  regresiones (verificado `== fuentes.emp`).
- **Almacén como dato de dominio:** `almacen_actual()` es opcional (None si el ERP no expone contexto
  de almacén); no se fuerza identidad donde no la hay.
- **No tocar la capa datos:** preserva la pureza de capas y evita acoplar `db` a `services`.

## 6. Compatibilidad

IOC v1/v2, IdentityAPI, CRM (III.1) y Smart Stock (III.2) **intactos**. Compras: comportamiento y
salida idénticos; multiempresa preservada; auditoría existente sin duplicar. Aditivo y reversible
(revertir = restaurar los 2 `_emp`; sin BD).

## 7. Resultado de pruebas (todas verdes)

| Prueba | Resultado |
|--------|-----------|
| `_emp` idéntico al histórico (2 servicios) | ✔ (`== fuentes.emp`) |
| Empresa / tienda / almacén vía adaptador | ✔ (trío) |
| IdentityContext | ✔ |
| Aislamiento multiempresa | ✔ |
| Eventos `compras.identidad.resuelta` (≥2 en bus) | ✔ |
| Telemetría (adaptador + IdentityAPI) | ✔ |
| Fallback robusto | ✔ |
| Compras funcional (recurrentes) intacto | ✔ |
| Compatibilidad IOC v1/v2 · CRM · Stock | ✔ |
| Smoke tests | ✔ **5 passed** |
| Regresiones | ✔ **cero** |

## 8. Informe técnico final

Compras adopta IOC en su capa de servicio con el mismo patrón validado en CRM y Smart Stock:
resolución de identidad (empresa/tienda/almacén) vía `IdentityAPI` mediante un adaptador fino, sin
alterar la lógica de negocio ni la GUI, con `IdentityContext`, telemetría, eventos significativos y
*fallback* a prueba de fallos. La cadena de aprovisionamiento (CRM → Stock → Compras) queda ya sobre
IOC como fuente única de identidad. Próximos: Producción y TPV con el mismo adaptador-plantilla.

### Anexo — Ficheros
- Nuevo: `src/services/compras/identidad_compras.py`
- Editados (seam `_emp`): `services/compras/{compras_pro,proveedores_pro}.py`
- Sin migración; sin cambios en IOC, lógica ni GUI de Compras.
- Evento: `compras.identidad.resuelta`.
