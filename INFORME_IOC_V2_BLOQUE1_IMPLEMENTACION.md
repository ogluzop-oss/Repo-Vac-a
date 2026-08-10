# IOC v2.0 — BLOQUE 1: Implementación de los Fundamentos (informe final)

> Continuación de `INFORME_IOC_V2_BLOQUE1.md` (7 entregables previos). Implementación aditiva
> (Strangler) de los cimientos del Identity Core. **No** se tocó documentos/TPV/CRM/RRHH/Stock/
> Producción/SOMA. Todo verificado; smoke 5 passed; cero regresiones.

---

## 1. Qué se ha construido (cimientos)

**Migración `0122_ioc_gobierno`** (aditiva/idempotente/reversible):
- Tabla `ioc_grupos_empresariales` — **nivel superior** de la jerarquía (holding/grupo/franquicia)
  con UUID permanente, estado de gobierno y propiedad.
- Columna `empresas.id_grupo` (NULL-able) — vincula empresa↔grupo sin romper multiempresa.
- Columnas de gobierno en `centros_trabajo`: `nivel` (GRUPO/CENTRO/SUBCENTRO/ZONA), `estado_gobierno`
  (ciclo oficial), `id_propietario`, `id_responsable_operativo`.
- Tabla `ioc_identidad_auditoria` — auditoría enriquecida (entidad, campo, **valor anterior/nuevo**,
  usuario, **IP**, **terminal**, empresa, fecha).

**Servicios de dominio nuevos en `src/services/identidad/`:**
- `gobierno.py` — estados oficiales + transiciones validadas, **soft delete** (transición a
  ELIMINACION_PENDIENTE; nunca DELETE físico), **guard de campos inmutables** (UUID/id_empresa/
  fecha_creacion), propiedad/responsable, `registrar_cambio_auditado`, `historial_identidad`.
- `grupos.py` — CRUD de grupo empresarial + `vincular_empresa` + `empresas_de_grupo`.
- `jerarquia.py` — `cadena_ascendente` (hasta grupo), `descendientes` (recursivo), `config_resuelta`
  (herencia con **override local**).
- `tipos.py` extendido — `ESTADOS_GOBIERNO`, `TRANSICIONES_GOBIERNO`, `NIVELES`, `TIPOS_GRUPO`,
  `CAMPOS_INMUTABLES` + validadores.
- `centros.py` — soporte aditivo de `nivel`/propiedad al crear centro (subcentros/zonas).

## 2. Principios IOC materializados

- **Permanente:** identidad = UUID (`ioc_grupos_empresariales.id`, `id_centro`, terminales/impresoras).
- **Desacoplada:** el UUID no lleva negocio; nombre/tipo/nivel son atributos.
- **Reutilizable:** todo cuelga del mismo núcleo (grupo→empresa→centro→…); sin ids paralelos.
- **Extensible:** `NIVELES`, `TIPOS_CENTRO`, `TIPOS_GRUPO` abiertos; nuevos tipos sin rediseño.
- **Auditada:** `ioc_identidad_auditoria` con valor anterior/nuevo, IP y terminal + `log_auditoria` + Event Bus.
- **Federada:** `id_grupo` + `id_empresa` (UUID) → SaaS/multiempresa/multipaís/multiholding sin migración futura.

## 3. Inversión de dependencias (Identity Core)

Verificado: `src/services/identidad/` importa solo `src.db.*` (datos), `src.services.eventos`/
`scheduler` (infra) y a sí mismo. **Cero** imports de módulos funcionales. Dirección `ERP → IOC`
garantizada. IOC queda oficialmente como Core transversal.

## 4. Gobierno de identidad (reglas oficiales activas)

- **Modificable:** nombre, alias, dirección, responsable, actividad, observaciones, códigos, tipo, nivel.
- **Inmutable (rechazado + auditado):** UUID, empresa propietaria, fecha de creación, identidad raíz.
- **Estados:** ACTIVO→SUSPENDIDO→ARCHIVADO→ELIMINACION_PENDIENTE→HISTORICO (transiciones validadas).
- **Soft delete:** nunca borrado físico.
- **Propiedad:** propietario/creador/modificador/responsable operativo, todos auditados.

## 5. Riesgos y estado

Todos los riesgos de la sección 6 del informe previo quedan mitigados y verificados: sin duplicar
entidades, sin motor de auditoría paralelo (detalle de dominio), `estado`/`archivado` v1 conservados,
sin borrado físico, inversión de dependencias intacta, migración reversible, multiempresa preservada,
módulos prohibidos no tocados.

## 6. Compatibilidad y pruebas (verificación end-to-end)

| Prueba | Resultado |
|--------|-----------|
| Compatibilidad IOC v1 | ✔ (servicios v1 intactos, migr 0121 vigente) |
| Multiempresa | ✔ (aislamiento por id_empresa) |
| UUID / centros / tiendas / almacenes existentes | ✔ (reutilizados, no duplicados) |
| Grupo empresarial + vinculación | ✔ (empresas_de_grupo=1 con empresa real) |
| Jerarquía ascendente | ✔ `SUBCENTRO→CENTRO→EMPRESA→GRUPO` |
| Jerarquía descendente | ✔ (2 descendientes recursivos) |
| Herencia con override local | ✔ (origen CENTRO) |
| Estados oficiales + transición válida/inválida | ✔ (ACTIVO→SUSPENDIDO OK; SUSPENDIDO→HISTORICO rechazada) |
| Soft delete (nunca físico) | ✔ (→ELIMINACION_PENDIENTE) |
| Guard de campos inmutables | ✔ (id_empresa rechazado) |
| Auditoría enriquecida (valor anterior/nuevo, IP, terminal) | ✔ (3 registros) |
| Event Bus | ✔ (eventos identidad.*) |
| Scheduler / RBAC | ✔ (sin cambios; jobs/permisos v1 vigentes) |
| Migración reversible | ✔ (revertir + reaplicar) |
| Smoke tests | ✔ **5 passed** |
| Regresiones | ✔ **cero** |

## 7. Qué NO se ha hecho (por diseño del bloque)

GUI, integración de consumidores (documentos/TPV/series/BI), IA/SOMA. El Bloque 1 solo construye los
cimientos; su adopción por los módulos será progresiva (Strangler) en bloques posteriores.

## 8. Resultado

**IOC queda oficialmente convertido en el núcleo de identidad corporativa (Identity Core)** de Smart
Manager AI: identidad permanente por UUID, desacoplada, reutilizable, extensible, auditada y federada;
jerarquía de 5 niveles (Grupo→Empresa→Centro→Subcentro→Zona→Terminal→Dispositivo→Usuario) con
navegación y herencia; gobierno con estados oficiales, soft delete e inmutabilidad. Base preparada
para décadas de crecimiento sin rediseños estructurales.

### Anexo — Ficheros del Bloque 1
- Migración: `src/database/migraciones/0122_ioc_gobierno.py`
- Servicios: `src/services/identidad/{gobierno,grupos,jerarquia}.py` + `tipos.py`/`centros.py` (aditivo)
- Informes: `INFORME_IOC_V2_BLOQUE1.md` (7 entregables) + este documento
- Sin cambios en módulos funcionales, documentos, TPV, SOMA, navegación.
