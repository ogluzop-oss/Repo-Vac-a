# IOC v2.0 — BLOQUE 1: Fundamentos de la Identidad Operativa Corporativa
## Entregables obligatorios (7 informes) — antes de implementar

> Este documento contiene los 7 entregables exigidos por el prompt del Bloque 1. La implementación
> descrita en la sección 7 se realiza **solo después** de este análisis, es aditiva (Strangler) y
> **no** toca documentos/TPV/CRM/RRHH/Stock/Producción/SOMA.

---

## 1. Informe de auditoría (estado actual — IOC v1 intacto)

**Verificado hoy:**
- Migración `0121_identidad_operativa` presente y registrada en `MODULOS`.
- Paquete `src/services/identidad/` con 8 módulos: `__init__, tipos, _base, centros, codigos,
  terminales, impresoras, identidad`.
- Modelo de datos v1 vigente: `centros_trabajo` extendido (tipo, jerarquía padre, alias, archivado,
  usuarios, fecha_modificacion) + `ioc_centro_codigos`, `ioc_terminales`, `ioc_impresoras`.
- Integración v1 operativa: RBAC (7 permisos `identidad.*`), Scheduler (3 jobs opt-in), Event Bus
  (`identidad.*`), auditoría (`log_auditoria`), multiempresa por `id_empresa`.
- Compatibilidad legada intacta: `configuraciones.ref_tienda/ref_almacen` + GUI + 2 consumidores
  visuales conservados.

**Conclusión:** IOC v1 permanece íntegro. No hay que reconstruir nada; el Bloque 1 se apoya sobre él.

## 2. Informe de arquitectura (inversión de dependencias)

**Regla oficial:** `ERP → IOC`. IOC nunca depende de un módulo funcional.

**Verificación (grep sobre `src/services/identidad/`):** IOC importa **exclusivamente**:
`src.db.*` (capa de datos: `conexion`, `empresa`, `centros`, `tiendas`, `usuario`),
`src.services.eventos` y `src.services.scheduler` (infraestructura), y `src.services.identidad.*`
(sí mismo). **Cero** imports de `crm|compras|inventario|ventas|tpv|rrhh|contratos|finanzas|
contabilidad|bi|mrp|calidad|gmao|sat|documental|tesoreria|logistica|produccion`.

**Resultado:** la inversión de dependencias se cumple. **No se detecta ninguna violación.** IOC queda
apto para ser declarado *Identity Core* transversal.

## 3. Informe de principios IOC (Identity Core)

| Principio | Cómo lo garantiza IOC v2 |
|-----------|--------------------------|
| **Permanente** | La identidad es un UUID (`id_centro`, `ioc_terminales.id`, `ioc_impresoras.id`, y nuevos `ioc_grupos_empresariales.id`). Nunca cambia aunque cambien nombre/propietario/dirección/actividad. |
| **Desacoplada** | El UUID no contiene negocio. Nombre/ciudad/tipo/referencia son **atributos** en columnas aparte, nunca la clave. |
| **Reutilizable** | Todos los módulos consumen IOC vía fachada `identidad_documento()`. Prohibido crear `id_tienda_local`/`id_centro_rrhh`/`id_tpv` paralelos. |
| **Extensible** | `TIPOS_CENTRO` es una lista abierta; añadir *Centro Veterinario, Puerto, Data Center…* no altera el núcleo (solo la enumeración). El `nivel` jerárquico es genérico. |
| **Auditada** | Toda mutación registra usuario/fecha/hora + (nuevo) IP/terminal/empresa/campo/valor anterior/valor nuevo en `ioc_identidad_auditoria`, además de `log_auditoria`. |
| **Federada** | Todo cuelga de `id_empresa` (CHAR(36) UUID) y (nuevo) `id_grupo` para holding/grupo/franquicia → SaaS/multiempresa/multipaís/multiholding sin migración estructural futura. |

## 4. Informe del modelo conceptual

**Jerarquía oficial (cada nivel existe independientemente):**

```
Grupo Empresarial (ioc_grupos_empresariales)   ← holding / grupo / franquicia
        ↓  (empresas.id_grupo)
Empresa (empresas)
        ↓
Centro Operativo (centros_trabajo, nivel=CENTRO)
        ↓  (centros_trabajo.id_centro_padre)
Subcentro (centros_trabajo, nivel=SUBCENTRO)
        ↓
Zona (centros_trabajo, nivel=ZONA)
        ↓
Terminal (ioc_terminales)
        ↓
Dispositivo / Impresora (ioc_terminales tipo dispositivo · ioc_impresoras)
        ↓
Usuario (usuarios)
```

**Representación de datos (sin duplicar entidades):**
- Grupo empresarial = tabla nueva `ioc_grupos_empresariales`; `empresas` gana columna `id_grupo`.
- Centro / Subcentro / Zona = **la misma tabla `centros_trabajo`** diferenciada por `nivel` +
  `id_centro_padre` (cadena de padres). No se crean tablas por nivel → extensible sin rediseño.
- Terminal/Dispositivo/Impresora/Usuario = entidades ya existentes (v1 + `usuarios`).

**Capacidades del modelo (servicio `jerarquia.py`):**
- **Navegación ascendente** (`cadena_ascendente`): zona→subcentro→centro→empresa→grupo.
- **Navegación descendente** (`descendientes`): todos los hijos recursivos de un nodo.
- **Herencia de configuración con override local** (`config_resuelta`): un atributo se resuelve
  subiendo por la cadena hasta encontrar el primero definido (el local gana).
- **Resolución jerárquica** de propietario/responsable/estado.

**Ejemplo soportado:** 1 empresa → 3 plantas (CENTRO) → 10 almacenes c/u (SUBCENTRO) → 15 terminales
c/u → varias impresoras. Todo comparte la identidad raíz (empresa/grupo) por `id_empresa`/`id_grupo`.

## 5. Informe de gobierno de identidad

**Documento de gobierno oficial (implementado como reglas en `gobierno.py`):**

**Modificable (atributos):** nombre, alias, dirección, responsable, actividad, observaciones, códigos
operativos, tipo, nivel.

**Inmutable (identidad — rechazado por el guard):** `UUID` (id), `id_empresa` (empresa propietaria),
`fecha_creacion`/`fecha_alta`, identidad raíz. Cualquier intento se rechaza y se audita.

**Estados oficiales (ciclo de vida único):**
`ACTIVO → SUSPENDIDO → ARCHIVADO → ELIMINACION_PENDIENTE → HISTORICO`.
**Nunca borrado físico**: el «delete» es una transición de estado (soft delete). El estado v1
(`estado`/`archivado`) se conserva; el ciclo oficial vive en `estado_gobierno`.

**Propiedad (todos auditados):** `id_propietario` (propietario), `usuario_creador` (creador),
`usuario_modificacion` (modificador), `id_responsable_operativo` (responsable operativo).

**Auditoría enriquecida:** cada cambio gobernado registra en `ioc_identidad_auditoria`:
entidad_tipo, entidad_id, campo, valor_anterior, valor_nuevo, usuario, IP, id_terminal, id_empresa,
fecha/hora. Complementa (no sustituye) `log_auditoria` y el Event Bus.

## 6. Riesgos detectados y mitigaciones

| Riesgo | Mitigación |
|--------|-----------|
| Duplicar entidad de centro por niveles | `nivel` en `centros_trabajo`; 0 tablas por nivel |
| Crear motor de auditoría paralelo | `ioc_identidad_auditoria` es **detalle de dominio**, no un bus/engine; sigue usando `log_auditoria` + Event Bus |
| Romper `estado`/`archivado` v1 | Se añade `estado_gobierno` aparte; los campos v1 se conservan |
| Borrado físico accidental | Prohibido: soft delete por transición de estado; sin `DELETE` |
| Violar inversión de dependencias | Verificado (sección 2); los servicios nuevos solo dependen de db/infra |
| Migración irreversible/no idempotente | CREATE IF NOT EXISTS + ALTER guardado + `revertir()` |
| Grupo empresarial rompe multiempresa | `id_grupo` es aditivo y NULL-able; empresas sin grupo siguen igual |
| Tocar módulos prohibidos | Bloque solo añade Core; documentos/TPV/CRM/RRHH/Stock/Producción/SOMA intactos |

## 7. Cambios concretos que se implementarán (foundations, aditivo)

**Migración `0122_ioc_gobierno`** (aditiva/idempotente/reversible):
- Tabla `ioc_grupos_empresariales` (UUID, nombre, tipo HOLDING/GRUPO/FRANQUICIA, estado_gobierno,
  propietario, soft-delete, fecha_creacion).
- Columna `empresas.id_grupo` (CHAR(36) NULL) — nivel superior de la jerarquía.
- Columnas en `centros_trabajo`: `nivel` (GRUPO/CENTRO/SUBCENTRO/ZONA, default CENTRO),
  `estado_gobierno` (ACTIVO por defecto), `id_propietario`, `id_responsable_operativo`.
- Tabla `ioc_identidad_auditoria` (detalle de cambios con valor anterior/nuevo, IP, terminal).

**Servicios nuevos en `src/services/identidad/`:**
- `gobierno.py` — estados oficiales + transiciones válidas, soft delete (nunca físico), guard de
  campos inmutables, setters de propiedad/responsable, `registrar_cambio_auditado()` (old/new/IP/term).
- `grupos.py` — CRUD de grupo empresarial + `vincular_empresa`.
- `jerarquia.py` — `cadena_ascendente`, `descendientes`, `config_resuelta` (herencia + override).

**NO se implementa aquí:** GUI, integración de consumidores (documentos/TPV/…), IA/SOMA. Solo cimientos.

**Pruebas:** compatibilidad IOC v1, multiempresa, UUID/centros/tiendas/almacenes existentes, Event Bus,
Scheduler, RBAC, jerarquía (ascendente/descendente/herencia), estados/soft-delete, guard de inmutables,
auditoría enriquecida, smoke, cero regresiones.
