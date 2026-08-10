# INFORME FINAL — Identidad Operativa de Centros (IOC)
## Implementación de la Infraestructura Central de Identidad

> Evolución de la primitiva «Asignar referencia» (auditada en
> `INFORME_AUDITORIA_IDENTIDAD_OPERATIVA.md`) hacia una infraestructura central de identidad, siguiendo
> el patrón Strangler. Todo aditivo, idempotente, reversible, multiempresa, auditado y verificado.

---

## 1. Arquitectura anterior

- **Único mecanismo de «identidad» de centro:** dos cadenas de texto libre globales
  (`configuraciones.ref_tienda` / `ref_almacen`), manuales, no únicas, no multiempresa (ignoraban
  `id_empresa`), con efecto **solo visual** (chip de menú + fallback de etiqueta de tienda).
- **Entidades reales dispersas y sin capa unificadora:** `empresas`, `centros_trabajo` (UUID
  `id_centro`, `codigo_centro`, sin `tipo` ni jerarquía), `tiendas`, `almacen`. Sin registro de
  terminales ni de impresoras. Sin servicio de dominio de identidad. Sin RBAC/eventos/jobs propios.

## 2. Arquitectura nueva

**Capa IOC = `src/services/identidad/`** (punto único de verdad; ninguna GUI accede a tablas):

| Módulo | Responsabilidad |
|--------|-----------------|
| `tipos.py` | Enumeraciones: TIPOS_CENTRO (18), TIPOS_CODIGO (11), TIPOS_DISPOSITIVO, TIPOS_IMPRESORA, ESTADOS |
| `_base.py` | Helpers: contexto multiempresa, auditoría, Event Bus, cursores |
| `centros.py` | CRUD de centro operativo (tipo, jerarquía padre, alias, archivado) sobre `centros_trabajo` |
| `codigos.py` | Códigos operativos MÚLTIPLES e INDEPENDIENTES por centro + resolución inversa |
| `terminales.py` | Identidad de TPV/PDA/dispositivos (UUID, MAC, IP, sw, heartbeat, reasignación) |
| `impresoras.py` | Registro de impresoras (tickets/etiquetas/A4/almacén/cocina) por centro/terminal |
| `identidad.py` | **Fachada**: `identidad_documento()` (cadena completa) + puente compat + jobs |

**Modelo de datos (migración `0121_identidad_operativa`):**
- **`centros_trabajo` EXTENDIDA** (no duplicada) con: `tipo`, `nombre_corto`, `alias`,
  `id_centro_padre`, `archivado`, `observaciones`, `usuario_creador`, `usuario_modificacion`,
  `fecha_modificacion`.
- **`ioc_centro_codigos`** — códigos independientes (VISIBLE/INTERNO/CORTO/FISCAL/CONTABLE/LOGISTICO/
  RRHH/TPV/DOCUMENTAL/BI/INTEGRACION), únicos por `(id_centro, tipo_codigo)`.
- **`ioc_terminales`** — UUID PK + código, centro, tipo, nombre, estado, última conexión, versión sw,
  última sync, IP, MAC, SO, nº serie, observaciones.
- **`ioc_impresoras`** — UUID PK + código, centro, terminal, tipo, nombre, backend, estado.

**Jerarquía representable:** Empresa → Centro (tipado + padre) → (Tienda/Almacén) → Terminal →
(Impresora) → Usuario. La identidad se basa en **UUID permanentes**; todos los códigos visibles son
atributos, nunca la identidad.

## 3. Componentes reutilizados

- `centros_trabajo` y `db.centros.crear_centro/actualizar_centro/obtener_centro` (secuencia CDT-NNN,
  `es_principal`) — **reutilizados por composición**, sin reescribir `db/centros.py`.
- `empresas` + `empresa.empresa_actual_id()` / `datos_corporativos()` — contexto y datos fiscales.
- `tiendas` (`codigo_tienda`, TenantContext) y `almacen` (`codigo_almacen`) — enlazados, no duplicados.
- **Event Bus** `services.eventos.publicar` — eventos `identidad.*` (nunca un bus paralelo).
- **JobRegistry / Scheduler** `scheduler_registry` — 3 jobs opt-in.
- **RBAC** `seguridad.catalogo.CATALOGO` + `sincronizar_catalogo` — 7 permisos nuevos.
- **Auditoría** `log_auditoria` — en cada mutación.
- **Feature legada** `configuraciones.ref_tienda/ref_almacen` + `obtener_referencias` — conservada y
  envuelta por el puente `referencia_legada()` / `migrar_referencia_a_centro()`.

## 4. Componentes añadidos

- Paquete de servicios `src/services/identidad/` (7 módulos).
- Migración `0121` (3 tablas nuevas + 9 columnas aditivas a `centros_trabajo`).
- 7 permisos RBAC `identidad.*`.
- 3 jobs de Scheduler (opt-in): `identidad_validacion_centros`, `identidad_verificacion_terminales`,
  `identidad_sincronizacion`.
- Eventos de dominio `identidad.centro_creado/modificado/archivado`, `identidad.codigo_asignado`,
  `identidad.terminal_registrado/asignado`, `identidad.impresora_registrada/asignada`.

## 5. Dependencias nuevas

- Ninguna de terceros. Solo `uuid` (stdlib). Dependencias internas: `conexion`, `empresa`, `centros`,
  `eventos`, `scheduler`, `log_auditoria` (todas ya existentes).

## 6. Riesgos detectados y mitigaciones

| Riesgo | Mitigación aplicada | Estado |
|--------|---------------------|--------|
| Duplicar la entidad centro | Se extendió `centros_trabajo`; 0 tablas paralelas | Resuelto |
| Romper `crear_centro`/`_PERMITIDOS` | Columnas aditivas; IOC crea vía `crear_centro`+UPDATE | Verificado |
| Bug legado multiempresa (ref_* global) | Todo IOC filtra por `id_empresa` | Verificado (E1=3/E2=1 aislados) |
| Migración no idempotente/irreversible | CREATE IF NOT EXISTS + ALTER guardado + `revertir()` | Verificado (revertir+reaplicar OK) |
| Jobs pesados no deseados | 3 jobs opt-in, deshabilitados por defecto | Verificado (en CATALOGO) |
| GUI accediendo a tablas | Toda la lógica en la fachada de servicios | Cumplido (sin GUI nueva) |
| Romper compatibilidad de `ref_*` | Conservados; puente sin borrado | Verificado (`referencia_legada` OK) |

## 7. Compatibilidad garantizada

- **Hacia atrás (Strangler):** `ref_tienda`/`ref_almacen`, su GUI y sus 2 consumidores visuales
  **intactos**. La fachada ofrece migración progresiva sin borrar nada.
- **Multiempresa:** aislamiento total por `id_empresa` (probado con 2 empresas).
- **Multitienda / multialmacén / multiterminal / multiimpresora:** N por empresa, sin límites; todo
  relacionado por UUID.
- **SaaS / Cloud / On-Premise / Híbrido:** modelo por `id_empresa` + UUID + job de sincronización
  reservado → preparado sin cambios estructurales futuros.
- **Certificado:** `smoke_test.py` = **5 passed**; sin regresiones; navegación/SOMA/TPV/documentos
  sin tocar.

## 8. Mejoras futuras recomendadas (no implementadas)

- GUI Enterprise (pestaña `QtEnterprisePanel`) para gestionar centros/terminales/impresoras,
  sustituyendo progresivamente la pantalla «Asignar referencia».
- Migración progresiva de consumidores: documentos/PDF, TPV, tickets, series fiscales y BI a
  `identidad_documento()` en lugar de textos libres.
- Flujos Workflow (alta de centro, cambio de responsable/código/estado, apertura/cierre).
- SOMA/Gemelo Digital: exponer la identidad como fuente de estado viva (infra ya lista; sin IA aún).
- Activación real del job de sincronización para federación SaaS multi-nodo.
- Enlace fuerte (FK/consistencia) centro↔tienda↔almacén y verificación de unicidad de códigos por tipo.

## 9. Estado de integración con cada módulo del ERP

**Infraestructura lista y consumible por fachada; integración por adopción progresiva (Strangler).**

| Módulo | Estado |
|--------|--------|
| Seguridad / RBAC | **Integrado** (7 permisos `identidad.*` sincronizados) |
| Scheduler / JobRegistry | **Integrado** (3 jobs opt-in) |
| Event Bus | **Integrado** (eventos `identidad.*` publicados) |
| Auditoría | **Integrado** (`log_auditoria` en cada mutación) |
| Empresa / Multiempresa | **Integrado** (contexto + `datos_corporativos`) |
| Tiendas / Almacenes | **Enlazado** (por `id_tienda`/tipo de centro) |
| Documentación | **Disponible** vía `identidad_documento()` (cadena completa) |
| Configuración (ref. legada) | **Compatibilidad total** + puente de migración |
| TPV / Terminales / Impresoras | **Infraestructura de identidad creada** (registro propio) |
| CRM, Compras, Ventas, Stock, Logística, MRP, Producción, Calidad, SAT, RRHH, Contratos, Nóminas, Tesorería, Contabilidad, BI, GMAO | **Preparado** (consumen la fachada cuando se migren; sin cambios forzados ahora) |
| SOMA / Copiloto / Gemelo Digital | **Preparado como fuente de estado** (sin IA todavía, por diseño) |
| Workflow | **Preparado** (flujos futuros sin cambios de arquitectura) |
| Navegación Enterprise | **Intacta** (sin tarjetas nuevas ni cambios) |

---

### Resultado

La función «Asignar referencia» evoluciona a una **Infraestructura Central de Identidad Operativa**:
identidad única, persistente (UUID), escalable, multiempresa y reutilizable para empresas, centros
(18 tipos + jerarquía), tiendas, almacenes, oficinas, delegaciones, terminales e impresoras, con
códigos operativos independientes por propósito. Compatible al 100 % con lo existente (Strangler),
sin duplicidades, sin motores paralelos, sin romper módulos certificados, e integrada con RBAC,
Event Bus, Scheduler, Auditoría y Multiempresa.

**Verificaciones:** migración 0121 aplicada, reversible y reaplicable; aislamiento multiempresa;
jerarquía; códigos independientes; terminales (heartbeat/reasignación); impresoras; archivado;
identidad documental completa; compat `ref_*`; RBAC (7 permisos en BD); Scheduler (3 jobs);
Event Bus; auditoría; **smoke 5 passed; cero regresiones**.

### Anexo — Ficheros
- Migración: `src/database/migraciones/0121_identidad_operativa.py`
- Servicios: `src/services/identidad/{__init__,tipos,_base,centros,codigos,terminales,impresoras,identidad}.py`
- RBAC: `src/services/seguridad/catalogo.py` (+7 permisos)
- Scheduler: `src/services/scheduler_registry.py` (+3 jobs, +1 registrador)
- Compatibilidad conservada: `src/db/conexion.py` (ref_*), `src/gui/gestion_usuarios.py` (GUI legada) — **sin cambios**
