# AUDITORÍA MAESTRA DE ARQUITECTURA — Smart Manager AI

Fecha 2026-07-29. Revisión de DISEÑO (no línea a línea). **Solo lectura: 0 modificaciones.** Diagnóstico
objetivo del ecosistema tras las fases AWS · SaaS · Entitlements · Canal Web · Marketplace · Portal Web.

## 0. Foto del sistema (evidencia)

- **~130k LOC**. `src/services/` = **81 subpaquetes**; `src/db/` = **55 módulos**; `src/gui/` = **70 ficheros**.
- Capas: `main.py`/`gui` (escritorio PyQt6) · `backend`+`api` (Flask REST/storefront) · `services` (lógica de
  dominio) · `db` (acceso a datos) · `platform` (prep. microservicios) · `portal_web` (Back Office) · `soma`
  (copiloto) · `sdk` (plugins) · `models` (vacío — los modelos viven por módulo).
- **Disciplina N7 fuerte y documentada**: fachadas únicas, "fuente única" repetida (articulos=stock/precio;
  web_config=marca; forecasting=motor único; eventbus sobre eventos), y notas explícitas "NO duplicidad".

---

## 1. Fortalezas de la arquitectura

1. **Separación por dominio consistente** (`services/<dominio>` + `db/<dominio>`), API-First (`/api/v1` que
   solo consume servicios), y tenant del token en toda la API.
2. **N7 real**: muy poca duplicación de CÓDIGO. Motores únicos (forecasting, Event Bus, Storage, Secret
   Manager, RBAC, Entitlements) reutilizados por fachadas; las capas nuevas COMPONEN, no reimplementan
   (p. ej. `portal_web.acceso` compone RBAC+Entitlements+licencia; `canal_web` compone conexiones/pubs/sync).
3. **Multi-tenant sólido** (404 tablas aisladas + `tenant_guard`; id_empresa/id_tienda del token; nunca por
   dominio).
4. **Extensibilidad**: Plugin SDK + Marketplace + Entitlements + Event Bus + Scheduler + capabilities facade →
   añadir módulos/canales es aditivo.
5. **AWS-ready sin acoplar el local**: backends por config (local por defecto), IaC gated, degradable.
6. **Ecosistema web ya delimitado** (WEB-01..04): Canal Web (orquestador), Marketplace (plugins +
   integraciones comerciales), Portal Web (Back Office), Portal Cliente, storefront.

## 2. Debilidades

1. **Proliferación de subpaquetes (81 en services/)** con **nombres colisionantes** → alta carga cognitiva y
   confusión (aunque casi todo sea layering intencional, no duplicación).
2. **Ficheros GUI enormes** (baja mantenibilidad): `ubicacion_tienda.py` 12.8k, `tpv.py` 8.9k,
   `gestion_usuarios.py` 7.0k, `recepcion_pale.py` 7.1k, `ventas.py` 3.4k.
3. **Frontera `db/` ↔ `services/` no perfectamente limpia**: `db/` (55 módulos) mezcla acceso a datos con algo
   de lógica; algunos servicios consultan BD directamente.
4. **`platform/` (prep. microservicios)** en gran parte latente (registry/discovery/gateway/routing/…): añade
   superficie sin uso operativo actual.
5. **Resto pendiente en TPV**: la config del Canal Web sigue embebida en `gui/tpv.py`
   (`_CanalWebConfigDialog`) — deuda conocida y diferida.

## 3. Duplicidades encontradas (mayormente de NOMBRE/concepto, no de código)

| Concepto | Módulos homónimos | Naturaleza |
|---|---|---|
| **catalogo** (×6) | `db.catalogo`(PIM) · `services.catalogo`(serialización) · `comercio_digital.catalogo`(ficha comercial) · `marketplace.catalogo`(plugins) · `seguridad.catalogo`(RBAC) · `autonomia.catalogo` | Dominios distintos; **NO duplicación de código**; confusión de nombre |
| **portal** (×5) | `portal_web`(Back Office) · `services.portal`(infra Fase V) · `api.routers.portal` · `facturacion.portal_cliente` · `gui.portal_empleado` | Solapamiento conceptual; `services.portal` (infra) sin frontend, redundante con `portal_web` |
| **scheduler** (×3) | `scheduler.py`(motor) · `scheduler_enterprise`(schedules) · `scheduler_registry.py`(catálogo jobs) | Layering; 2 "schedulers" confunden |
| **eventos / eventbus** | `services.eventos`(bus interno) · `services.eventbus`(fachada Corporate + realtime + distribución) | 2 "buses" por nombre; eventbus es fachada sobre eventos |
| **ia / prediccion / inteligencia** | `ia`(análisis) · `prediccion`(motor) · `inteligencia`(ledger decisiones) | Layering IA documentado; nombres poco distinguibles |
| **stock / inventario** | `db.stock` · `services.stock`(IOC) · `services.inventario` · `prediccion.stock` | Solapamiento; `articulos` es la fuente única real |
| **finanzas / tesoreria / contabilidad** | 3 paquetes + `tesoreria.contabilidad.py` | Dominios contiguos; fronteras difusas |
| **produccion / mrp** | `services.produccion` · `services.mrp` | Posible solape (fabricación) |
| **cloud** (×4) | `platform.cloud` · `cloud_manager` · `observabilidad.cloud` · `saas_global` | Concepto "cloud" disperso |
| **integraciones** | `services.integraciones` · `comercio_digital.integraciones_comerciales` · `marketplace.integraciones_comerciales` | Nombres próximos; responsabilidades distintas |

**Conclusión clave**: la deuda dominante NO es duplicación de lógica (N7 la evita), sino **colisión de nombres
y proliferación de módulos-capa** → coste de comprensión y riesgo de "reconfusión".

## 4. Módulos que PODRÍAN fusionarse (propuesta, sin decidir)

- **`services.portal` (infra Fase V) → dentro de `portal_web`**: `services.portal` define tipos/scopes de
  portal sin frontend; `portal_web` ya es el Back Office. Un único paquete "portal" (con subcapas cliente/
  empleado) reduciría el ×5.
- **`eventos` + `eventbus`**: unificar bajo un único nombre/espacio (`eventbus` como fachada canónica, `eventos`
  como transporte interno) o renombrar para dejar clarísima la relación fachada→bus.
- **`scheduler` + `scheduler_enterprise` + `scheduler_registry`**: consolidar en un paquete `scheduler/` con
  submódulos (motor/schedules/registry) en vez de 3 módulos hermanos.
- **`ia` + `prediccion` + `inteligencia`**: mantener las 3 capas pero bajo un paraguas `ia/` (`ia.analisis`,
  `ia.prediccion`, `ia.decisiones`) para que el nombre exprese la jerarquía.
- **`stock` (IOC) + `inventario`**: fusionar los dos "enriquecimientos" de inventario si no aportan fronteras
  reales.
- **`produccion` + `mrp`**: evaluar unificar bajo `fabricacion/`.

## 5. Módulos que PODRÍAN dividirse

- **GUI grandes** → dividir por pestañas/subpantallas: `ubicacion_tienda.py` (12.8k), `tpv.py` (8.9k),
  `gestion_usuarios.py` (7.0k), `recepcion_pale.py` (7.1k), `ventas.py` (3.4k), `menu_principal.py` (2.0k).
  Alinear con la regla del proyecto (Enterprise Shell + `gui/components`).
- **`gui/tpv.py`**: extraer `_CanalWebConfigDialog` (y `_GestionPedidosOnlineDialog`) a `gui/canal_web_gui.py`
  (ya iniciado en WEB-02) — deuda explícita.
- **`db/conexion.py` (2.4k)**: separar bootstrap/DDL, pool y helpers.

## 6. Dependencias innecesarias / acoplamientos

- **UI Canal Web ↔ TPV** (`_CanalWebConfigDialog` usa helpers privados de `tpv.py`): acoplamiento estructural
  que bloquea la extracción limpia.
- **GUIs monolíticas** acoplan muchas responsabilidades en un fichero (alto fan-in de helpers privados).
- **No se detectan dependencias circulares de servicio evidentes** (patrón en capas articulos→catalogo→
  storefront/canal; eventbus→eventos unidireccional). Recomendable verificar con herramienta de grafos
  (p. ej. `pydeps`/import-linter) para confirmar objetivamente.
- **`platform/` gateway/routing/discovery**: acoplamiento potencial futuro si se activa sin necesidad real.

## 7. Responsabilidades mal repartidas

- **TPV** hospeda configuración de Canal Web (no es su responsabilidad) — a extraer.
- **`db/`** contiene lógica que en un diseño estricto iría en `services/` (frontera data/negocio difusa en
  algunos módulos).
- **`services.portal`** define acceso/scopes de portal pero **no lo consume nadie** (ni router ni frontend) →
  responsabilidad "huérfana" solapada con `portal_web`.
- **Catálogo**: 3 capas de comercio correctas (PIM/serialización/ficha) pero el nombre no comunica la jerarquía
  → responsabilidad clara en código, confusa en nomenclatura.

## 8. Oportunidades de simplificación

1. **Namespacing por concepto** (mayor ROI, bajo riesgo): agrupar homónimos bajo paquetes paraguas
   (`catalogo/*`, `portal/*`, `scheduler/*`, `ia/*`) **conservando contratos públicos** (Strangler/alias).
2. **Adelgazar GUIs** con el Enterprise Shell + componentes (ya es regla del proyecto).
3. **Glosario/ADR de nomenclatura**: documento único que fije qué significa cada "catalogo/portal/scheduler/
   evento" (reduce el riesgo de "reconfusión" que la propia base ya intenta mitigar con notas inline).
4. **Consolidar `cloud`** disperso bajo `platform/` o `services/cloud/`.
5. **Retirar/segregar `platform/` latente** hasta que haya una necesidad real (reduce superficie).

## 9. Riesgos arquitectónicos futuros

- **Carga cognitiva creciente**: 81 paquetes + colisiones de nombre → onboarding lento y riesgo de duplicar por
  desconocimiento (mitigado hoy por notas inline, frágil a escala de equipo).
- **GUIs monolíticas**: coste de cambio alto y foco de regresiones (recuérdese el bug SIP con slots ñ, y el
  acoplamiento Canal Web↔TPV).
- **`db/` como cajón**: si sigue creciendo mezclando datos+lógica, dificulta el paso futuro a repositorios/
  microservicios.
- **`platform/` microservicios** puede inducir a una migración prematura innecesaria; el monolito modular
  actual es adecuado.
- **Escalabilidad de tiempo real**: SSE single-instance; multi-instancia requiere el broker (ya preparado,
  no activo) — no romper el patrón fachada.

## 10. Plan recomendado de refactorización (SIN ejecutar — priorizado por ROI/riesgo)

| Prioridad | Acción | Riesgo | Nota |
|---|---|---|---|
| P1 | **ADR de nomenclatura + glosario** (catalogo/portal/scheduler/eventos/ia/stock) | Muy bajo | 0 código; máxima claridad |
| P1 | **Extraer `_CanalWebConfigDialog` de `tpv.py`** a `gui/canal_web_gui.py` (Strangler) | Medio | deuda ya conocida; validar suite |
| P2 | **Fusionar `services.portal` en `portal_web`** (o marcar deprecado) | Bajo | eliminar responsabilidad huérfana |
| P2 | **Consolidar scheduler** (paquete con motor/schedules/registry) conservando fachadas | Bajo-Medio | alias de compatibilidad |
| P2 | **Dividir GUIs grandes** por pestañas con Enterprise Shell (empezar por `ubicacion_tienda`, `tpv`) | Medio | por Strangler, con tests offscreen |
| P3 | **Namespacing paraguas** `ia/{analisis,prediccion,decisiones}`, `catalogo/*` (alias) | Medio | conservar contratos públicos |
| P3 | **Aclarar frontera `db/` vs `services/`** (mover lógica de `db/` a `services/` gradualmente) | Medio-Alto | incremental, sin big-bang |
| P4 | **Revisar `platform/` / `cloud` disperso**: consolidar o congelar hasta necesidad real | Bajo | reduce superficie |
| P4 | **Grafo de dependencias objetivo** (import-linter/pydeps) para confirmar ausencia de ciclos | Muy bajo | evidencia automatizable |

**Regla transversal**: cualquier refactor debe seguir el **Strangler Pattern + deprecación** (ya mandado por
CLAUDE.md) y **conservar contratos públicos** (v_id/rutas/firmas), con la suite verde en cada paso.

---

## Veredicto

Arquitectura **sólida y coherente en el fondo** (N7 real, multi-tenant fuerte, API-First, AWS-ready,
extensible), con deuda **principalmente de FORMA**: **nomenclatura colisionante**, **proliferación de
módulos-capa** y **GUIs monolíticas**. No hay duplicación de lógica grave ni ciclos evidentes. El mayor ROI de
refactorización está en **clarificar nombres (ADR/namespacing)** y **adelgazar/extraer GUIs** (empezando por la
deuda Canal Web↔TPV) — todo por sustitución progresiva, sin reescrituras. La base soporta bien más empresas/
tiendas/usuarios/módulos/canales/IA y la evolución a móvil/AWS/multi-instancia sin rediseño estructural.

*(Informe de solo lectura. No se ha modificado, movido ni eliminado ningún componente.)*
