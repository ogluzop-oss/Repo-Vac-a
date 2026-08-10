# INFORME TÉCNICO PREVIO — Identidad Operativa de Centros (IOC)
## Fase 2 — Antes de desarrollar

> Basado en la re-auditoría de Fase 1 (verificada hoy). No se ha modificado código todavía.

---

## 1. Elementos existentes (reutilizables)

| Entidad | Tabla | Aporta | Uso IOC |
|---------|-------|--------|---------|
| Empresa | `empresas` (`id_empresa` CHAR(36) UUID, `codigo_empresa`) | Raíz multi-tenant | Nivel 1 de la jerarquía |
| **Centro de trabajo** | `centros_trabajo` (`id_centro` UUID, `codigo_centro` CDT-NNN, `id_empresa`, `id_tienda` opc, `es_principal`, dirección + códigos fiscales) | **Entidad centro ya existente con UUID** | **Ancla canónica del centro IOC** |
| Tienda | `tiendas` (`id`, `codigo_tienda`, `id_empresa`) + TenantContext | Multitienda real (selector F1) | Atributo/enlace del centro tipo TIENDA |
| Almacén | `almacen` (`id`, `codigo_almacen`, `tipo_almacen`, `id_empresa`, `id_tienda`) | Multialmacén real | Atributo/enlace del centro tipo ALMACÉN |
| Versiones terminal | `terminal_versiones` (`id_empresa`,`id_tienda`,`version_sw`,`ultima_sync`) | Versionado sw/db por tienda | Fuente para heartbeat de terminal |
| Impresora (driver) | `services/perifericos/impresora.py` (`ImpresoraConfig`, backends) | Driver de impresión runtime | Se conserva; IOC añade el **registro** de impresoras |
| Terminal de cobro | `services/tpv/card_terminal_service.py` | Driver de pago (Redsys/Stripe) | Distinto de la identidad de TPV; no se toca |
| Datos corporativos | `empresa.datos_corporativos()` → `centro_codigo` | Identidad fiscal a documentos | IOC amplía la identidad documental |
| RBAC | `catalogo.py::CATALOGO` + `permisos` | Catálogo canónico sincronizable | Se añaden 7 permisos `identidad.*` |
| Event Bus | `services/eventos.publicar(tipo, *, ref_entidad, ref_id, id_empresa, payload)` | Bus único | IOC publica eventos de identidad |
| Scheduler/JobRegistry | `services/scheduler` + `scheduler_registry` | Jobs opt-in con metadatos | 3 jobs IOC (deshabilitados por defecto) |
| Auditoría | `db.conexion.log_auditoria(modulo,accion,tabla,detalle)` | Traza | En cada mutación IOC |
| Compat referencia | `configuraciones.ref_tienda/ref_almacen` + `obtener/guardar_referencia` | Feature legada | **Se conserva** (Strangler), IOC la envuelve |

## 2. Elementos reutilizables directamente

- `centros_trabajo` como registro de centros (se **extiende**, no se duplica).
- `db.centros.crear_centro` (secuencia `codigo_centro`, lógica `es_principal`) → se reutiliza y se
  complementa con los nuevos atributos IOC vía UPDATE (sin tocar `db/centros.py`).
- `empresa.empresa_actual_id()`, `empresa.tienda_actual_id()`, `tiendas.obtener_tienda` → contexto.
- Event Bus, JobRegistry, RBAC catalog, `log_auditoria` → integración estándar.

## 3. Dependencias

- Nuevas tablas dependen de `empresas`/`centros_trabajo` (por `id_empresa`/`id_centro`).
- Servicios IOC dependen de `conexion`, `empresa`, `centros`, `eventos`, `scheduler`, `log_auditoria`.
- Sin dependencias nuevas de terceros (solo `uuid` de stdlib).

## 4. Módulos afectados (en esta fase, mínimamente e incrementalmente)

- **Añadidos (nuevos):** `src/services/identidad/*`, migración `0121`.
- **Extendidos aditivamente (sin cambiar lógica):** `centros_trabajo` (+columnas), `catalogo.py`
  (+7 permisos), `scheduler_registry` (+3 jobs).
- **NO tocados:** `db/centros.py`, `db/tiendas.py`, `db/conexion.py::obtener/guardar_referencia`,
  GUI de «Asignar referencia», TPV, documentos, SOMA, navegación. La integración con los ~30 módulos
  se hará **progresivamente** vía la fachada de servicios (esta fase deja la infraestructura y el
  puente de compatibilidad listos; no reescribe consumidores).

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|-----------|
| Duplicar `centros_trabajo` | NO se crea tabla paralela: se extiende la existente + tablas satélite |
| Romper `crear_centro` (`_PERMITIDOS`) | Columnas aditivas; IOC crea vía `crear_centro`+UPDATE, sin tocar el módulo |
| Multiempresa mal resuelta (bug legado ref_*) | Todo IOC filtra por `id_empresa` desde el primer día |
| Migración no idempotente | `CREATE IF NOT EXISTS` + ALTER guardado por `information_schema` + reversible |
| Jobs pesados no deseados | 3 jobs opt-in, deshabilitados por defecto en JobRegistry |
| GUI accede a tablas | Prohibido: toda lectura/escritura vía `services/identidad` (fachada) |
| Romper compatibilidad `ref_*` | Se conservan; la fachada ofrece `identidad_documento()` y un puente hacia ref_* |

## 6. Plan de implementación

1. **Migración 0121** — extender `centros_trabajo` (tipo, nombre_corto, alias, id_centro_padre,
   archivado, observaciones, usuario_creador/modificacion, fecha_modificacion) + tablas
   `ioc_centro_codigos`, `ioc_terminales`, `ioc_impresoras`.
2. **Servicios de dominio** `src/services/identidad/`: `tipos` (enums), `centros`, `codigos`,
   `terminales`, `impresoras`, `identidad` (fachada + jobs + puente compat).
3. **RBAC**: +7 permisos `identidad.*` en `CATALOGO`.
4. **Scheduler**: +3 jobs (`identidad_validacion_centros`, `identidad_verificacion_terminales`,
   `identidad_sincronizacion`) en `scheduler_registry` (opt-in).
5. **Event Bus + auditoría** en cada mutación.
6. **Pruebas** (multiempresa, multitienda, almacenes, terminales, impresoras, cambio de centro/tienda,
   auditoría, event bus, scheduler, RBAC, compat ref_* y documentos) + **smoke**.
7. **Informe final** `INFORME_IOC_IMPLEMENTACION.md` (9 secciones).

**Alcance de esta fase:** construir la infraestructura y la fachada reutilizable + puente de
compatibilidad. NO se migran aún los 30 módulos consumidores (integración progresiva posterior), NO
se añade inteligencia a SOMA (solo se deja disponible como fuente de estado), NO se crea GUI nueva.
