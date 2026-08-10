# IOC v2.0 — BLOQUE III.1: Auditoría previa de integración IOC ↔ CRM

> Auditoría exclusiva (sin cambios de código). Objetivo: localizar los puntos de identidad del CRM
> antes de la adopción progresiva (Strangler) del motor IOC.

## 1. Superficie del CRM

12 servicios (`src/services/crm/`): `actividades, analitica, automatizacion, campanias, crm_saas,
crm_scoring, leads, objetivos, oportunidades, pipeline, rutas` (+ `__init__`). GUI: `crm_dashboard.py`,
`clientes_gui.py`. Datos: `db/clientes.py` y tablas `crm_*`.

## 2. Uso de identidad detectado

- **158** referencias a identidad; **todas** giran en torno a `id_empresa`.
- **El CRM NO usa `id_tienda`, `id_almacen`, `id_centro`, `codigo_tienda`, `codigo_centro`,
  `centros_trabajo` ni `ref_tienda`** (grep sin resultados). Es un módulo **puramente empresa-scoped**.
- **Punto único de resolución de identidad:** el helper `_emp(id_empresa)` replicado en cada módulo:
  - **Variante simple (7 módulos)** — `actividades, analitica, automatizacion, crm_scoring, leads,
    oportunidades, pipeline`: `return id_empresa or empresa_actual_id()`.
  - **Variante con abstracción (3 módulos)** — `campanias, objetivos, rutas`: `return fuentes.emp(...)`
    (resolver del Gemelo, con *fallback*).

## 3. Accesos directos

- **123** accesos SQL/`obtener_conexion` en CRM, todos a **tablas propias del CRM** (`clientes`,
  `crm_campanias`, `crm_oportunidades`, `crm_objetivos`, `crm_rutas`, `crm_scoring`, …). **Ninguno** a
  tablas IOC, Repository ni identidad.
- No hay acceso del CRM al `IdentityRepository` ni a UUID/códigos de centros (no aplica: no usa centros).

## 4. Duplicidades de identidad

- La única duplicidad es el helper `_emp` copiado 10 veces (2 estilos). No hay ids de identidad
  paralelos (`id_empresa` es el canónico multiempresa). No hay `id_tienda_local`/`id_centro_crm`.

## 5. Conclusión de la auditoría

La integración IOC↔CRM es de **bajo riesgo y alcance quirúrgico**: el único seam de identidad es la
resolución de empresa (`_emp`). El resto de accesos SQL son de **dominio CRM** (clientes/oportunidades)
y **no deben migrarse** (sería cambiar la lógica funcional, prohibido). Plan:

1. Crear un adaptador **CRM↔IOC** (`src/services/crm/identidad_crm.py`) sobre `IdentityAPI`:
   `empresa_id()` (resolución de empresa vía IOC, comportamiento idéntico + telemetría), `contexto()`
   e `identidad_cliente()` (resolución significativa vía `IdentityAPI`, con eventos).
2. Migrar los **7 `_emp` simples** para delegar en el adaptador (behavior-preserving, con *fallback*).
3. Dejar las **3 variantes `fuentes.emp`** documentadas para migración posterior (ya usan abstracción).
4. Multiempresa: se preserva (el adaptador devuelve el mismo `id_empresa`; sin fugas).
5. Eventos/telemetría: en las resoluciones significativas (no en el `_emp` de camino caliente).

**No se migra** el acceso a datos de dominio del CRM (clientes/oportunidades): fuera del alcance de
identidad y protegido por la regla de no tocar la lógica funcional.
