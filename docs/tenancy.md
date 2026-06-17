# Decisión de tenancy (E1.5) — Smart Manager AI

**Decisión formal de esta etapa: OPCIÓN A — el producto se declara MONO‑EMPRESA
on‑premise.** No se implementa el enforcement multi‑empresa completo en E1.

## Contexto
La base de datos es compartida y el aislamiento se basa en columna `id_empresa` +
`TenantContext`. El bloque fiscal (C3) y buena parte del núcleo (catálogo, clientes,
stock de tienda, sesiones, pedidos online, configuración) **sí** aplican aislamiento.
Quedan puntos sin enforcement que solo afectan a despliegues **multi‑empresa en BD
compartida**.

## Evidencia (auditoría, estado real del repo)

| Área | Aislada | Evidencia |
|---|---|---|
| Fiscal (C3) | ✅ | cadena/cola/config/certificados por `id_empresa` (tests) |
| Catálogo / clientes / stock_tienda / pedidos online / sesiones | ✅ | filtran por `id_empresa` |
| **articulos** | ❌ | **PK global `codigo` sin `id_empresa`**; **81 sentencias SQL en 24 ficheros** (15 en `ubicacion_tienda.py`, 15 en `conexion.py`, 10 en `recepcion_pale.py`…); FKs desde catálogo/stock/reab/mermas |
| **reabastecimiento** (reab_config/propuestas/schedule) | ❌ | 13 funciones, 0 referencias a `id_empresa` |
| **operaciones** | ❌ | 1 función, sin `id_empresa` |

## Coste real de completar el enforcement (Opción B)
- **articulos (dominante):** cambiar PK `codigo` → compuesta o añadir `id_empresa` y
  propagar a **~81 consultas** + FKs dependientes + pantallas monolíticas
  (`ubicacion_tienda` 12.5k LOC, `recepcion_pale` 7k). **Complejidad ALTA, riesgo ALTO**
  (migración de datos + reescritura amplia) → es una **épica propia**.
- **reabastecimiento + operaciones:** migración aditiva (columnas) + filtrar ~14
  consultas. Complejidad MEDIA, pero **depende de articulos** (reab referencia
  `articulos.codigo`).

## Riesgo real de explotación
- **Mono‑empresa on‑premise (escenario objetivo de esta etapa):** **NULO** (un solo
  tenant; no hay datos de otras empresas que filtrar).
- **Multi‑empresa en BD compartida / SaaS:** **ALTO** (fuga de datos entre empresas en
  artículos/reabastecimiento/operaciones). Bloqueante para SaaS.

## Recomendación
**Opción A — declarar oficialmente MONO‑EMPRESA en esta etapa.** El esfuerzo restante
(sobre todo `articulos`) **no es pequeño ni claramente rentable dentro de E1**; la
directiva E1.5 indica no implementar el aislamiento salvo que lo fuera. En
mono‑empresa el riesgo es nulo, por lo que **no procede** abordarlo ahora.

## Implicaciones / guardarraíles
- El producto se comercializa/usa como **una empresa por instalación**.
- **No** habilitar varias empresas sobre la misma BD hasta completar la épica de
  aislamiento (futuro, requisito previo de SaaS — ver `[[project_*]]`/roadmap).
- Cuando se aborde SaaS: **épica “Aislamiento multi‑tenant”** = (1) `articulos` por
  empresa (PK/FK/consultas), (2) reabastecimiento/operaciones, (3) barrido de lecturas.

## Estado
Decisión tomada y registrada. Cumple el criterio de cierre de E1 “decisión formal
sobre tenancy”. **No se ha modificado código de aislamiento.**
