# Pull Request — Suite Enterprise Smart Manager AI

> **Fecha de generación:** 2026-06-27 · **Actualizado:** 2026-06-27
> **Rama:** `feat/erp-enterprise-suite` → `main`
> **Último commit de la rama:** `84c13b4` — `docs(pr): documentación oficial del PR de la suite enterprise`
>
> ### Estado de fusión (actualizado)
> - ✅ **PR #1 fusionado en `main`** (merge `271469c`; padres `1b42d51` + `c866b20`) — 14 primeros commits.
> - ✅ **PR #2 fusionado en `main`** (merge `2989fef`) — `32b73e0` (endurecimiento OAuth / Secret Manager) + `84c13b4` (`PULL_REQUEST.md`).
> - ✅ **Todo el trabajo funcional está ya en `main`.** No queda nada funcional pendiente.
> - ✅ **Merge limpio verificado** (`git merge-tree`, sin conflictos en ningún momento).
> - ⚠️ Los merges se realizaron con **commit de merge** (no fast-forward), por la existencia de los nodos de merge `271469c`/`2989fef`.
> - 🔁 Único delta restante en `feat`: commits de **sincronización de esta documentación**; pueden fusionarse con un PR de docs o descartarse eliminando la rama.

---

## Título del Pull Request

**feat: Suite Enterprise Smart Manager AI — Fiscalidad AEAT, Seguridad/RBAC, Workflow/BPM, BI/SaaS, DR/CRM, MRP/Calidad, GMAO/SAT, Finanzas avanzadas, BI Corporativo, Resiliencia y UX-TPV**

---

## 1. Resumen ejecutivo

Esta rama eleva Smart Manager AI de ERP operativo a **plataforma empresarial multiempresa/SaaS completa**, añadiendo 12 bloques funcionales de forma **estrictamente aditiva, idempotente y reversible**, sin alterar la lógica ya validada (kárdex, lotes, compras, ventas, fiscalidad Verifactu/Facturae, contabilidad PGC, tesorería/SEPA).

- **16 commits temáticos** (14 ya fusionados vía PR #1 + 2 pendientes en PR #2) · **258 ficheros** · **+25.216 / −1.103 líneas**
- **16 migraciones nuevas** (0052 → 0067), todas `CREATE/ALTER … IF NOT EXISTS`
- **16 paquetes de servicios** + **8 servicios transversales** + **16 nuevas GUIs**
- **43 nuevos ficheros de test** · **suite: 879 passed / 0 fail**
- **Incidente de seguridad resuelto**: purgada del 100% del historial una credencial OAuth real que existía desde el commit inicial (rotada en Google Cloud).

## 2. Objetivos alcanzados

- ✅ Completar el cumplimiento fiscal español (modelos AEAT 303/390/111/190/347/349).
- ✅ Seguridad de nivel empresarial: RBAC/ACL, MFA TOTP, RGPD, observabilidad.
- ✅ Motor de aprobaciones (BPM) configurable por empresa.
- ✅ Plataforma BI + Data Warehouse + SaaS multitenant con enforcement de planes.
- ✅ Continuidad de negocio: Disaster Recovery + offline-first/resiliencia.
- ✅ Cobertura industrial: MRP/Fabricación, Calidad, GMAO, SAT/Helpdesk.
- ✅ Finanzas avanzadas (presupuestos, financiación, crédito, ratios, What-If).
- ✅ BI Corporativo (DW unificado, OLAP, consolidación multiempresa).
- ✅ UX multidispositivo: TPV ampliado, navegación, sidebar colapsable, responsive/High-DPI.
- ✅ Endurecimiento del correo OAuth (env/secret-manager, sin JSON en disco).

## 3. Bloques incluidos en esta rama

| Bloque | Commit | Migración |
|---|---|---|
| DevOps/CD (Docker, gunicorn/wsgi, CI build) | `chore(devops)` | — |
| Fiscalidad AEAT | `feat(aeat)` | 0052–0054 |
| Seguridad/Observabilidad | `feat(seguridad/observabilidad)` | 0055, 0060 |
| Workflow/BPM + Comunicaciones | `feat(workflow/comunicaciones)` | 0056, 0057 |
| BI + SaaS | `feat(bi/saas)` | 0058, 0059 |
| Disaster Recovery + CRM | `feat(dr/crm)` | 0061 |
| MRP/Fabricación + Calidad | `feat(mrp/calidad)` | 0062 |
| GMAO + SAT/Helpdesk | `feat(gmao/sat)` | 0063 |
| Finanzas avanzadas + BI Corporativo | `feat(finanzas/bi-corp)` | 0064, 0065 |
| Resiliencia / Offline-first | `feat(resiliencia)` | 0066 |
| UX-TPV-01 (TPV/navegación/responsive) | `feat(ux)` | 0067 |
| Endurecimiento correo OAuth | `feat(correo)` | — |

## 4. Funcionalidades nuevas incorporadas

- **AEAT**: generación de modelos 303, 390, 111, 190, 347, 349 + infraestructura común de declaraciones; retenciones de compras e IVA intracomunitario.
- **Seguridad**: roles/permisos/grupos/ACL, motor `autorizacion.puede()`, MFA TOTP + códigos de recuperación, security headers, anomalías, RGPD, secret_manager.
- **Observabilidad**: logging JSON con correlation-id, `/health`/`/metrics` Prometheus, alertas/incidentes, OpenTelemetry degradable.
- **Workflow/BPM**: motor de aprobaciones multinivel por importe, delegación, SLA, bandeja y diseñador.
- **Comunicaciones**: notificaciones, scheduler, correo SMTP/IMAP + plantillas, mensajería, tareas, calendario, webhooks salientes con HMAC, conectores.
- **BI + SaaS**: Data Warehouse, motor de KPIs, forecasting Prophet; planes BASIC/PLUS/PRO con enforcement real, billing/dunning, branding, métricas, backup/restore por tenant.
- **DR + CRM**: PITR/snapshots, storage off-site, drills; pipeline comercial (leads/oportunidades/actividades/scoring IA).
- **MRP/Calidad**: BOM multinivel, centros/rutas, órdenes de fabricación integradas al kárdex real; inspecciones/NC/CAPA/auditorías/trazabilidad.
- **GMAO/SAT**: activos, planes preventivos, OT con repuestos por kárdex, KPIs MTTR/MTBF; tickets/SLA/colas/KB/portal cliente.
- **Finanzas avanzadas**: presupuestos (escenarios/versiones), préstamos/leasing (amortización francesa → vencimientos tesorería), crédito/scoring, ratios EBITDA/ROE/CCC, simulación What-If, IA financiera.
- **BI Corporativo**: DW unificado `dw_hechos`, OLAP (cubos/drill/slice/dice), consolidación multiempresa, alertas explicables, export PDF/Excel/CSV/JSON.
- **Resiliencia**: offline-store SQLite por tienda, outbox/inbox, sync idempotente al kárdex, event sourcing, circuit breakers, watchdog/autoheal, edge node, chaos testing, RPO/RTO.
- **UX/TPV**: tarjetas CLIENTES/Mostrar stock/Venta online + Mov. efectivo/Cambio cajero; Gestión Caja como ventana propia; sidebar colapsable global persistente; responsive/High-DPI.

## 5. Migraciones (contexto 0045 → 0067)

> **Nota:** 0045–0051 (Tesorería/Bancos/SEPA) **ya están en `main`** y se incluyen como contexto. Las migraciones **NUEVAS de este PR son 0052 → 0067 (16)**.

| Migración | Contenido | ¿En este PR? |
|---|---|---|
| 0045–0051 | Tesorería: cuentas, movimientos, vencimientos, pagos, conciliación, SEPA, endurecimiento | base (ya en main) |
| 0052 | AEAT declaraciones | ✅ |
| 0053 | Compras / retención | ✅ |
| 0054 | Intracomunitario | ✅ |
| 0055 | RBAC | ✅ |
| 0056 | Workflow | ✅ |
| 0057 | Comunicaciones | ✅ |
| 0058 | BI Data Warehouse | ✅ |
| 0059 | SaaS | ✅ |
| 0060 | Observabilidad / Seguridad | ✅ |
| 0061 | DR + CRM | ✅ |
| 0062 | MRP / Calidad | ✅ |
| 0063 | GMAO / SAT | ✅ |
| 0064 | Finanzas avanzadas | ✅ |
| 0065 | BI Corporativo | ✅ |
| 0066 | Resiliencia | ✅ |
| 0067 | Preferencias de usuario | ✅ |

Verificadas en 3 escenarios: BD vacía (aplica las 16), BD con datos (idempotente), upgrade (re-aplica 0063–0067 sin efectos colaterales).

## 6. Nuevas tablas (agrupadas por módulo)

> Detección directa: **~31 `CREATE TABLE`**; varias migraciones crean conjuntos de tablas por dominio mediante plantillas, por lo que el total efectivo es mayor.

- **AEAT (0052–0054)**: cabecera/detalle de declaraciones; retenciones de compras; operaciones intracomunitarias.
- **Seguridad/RBAC (0055)**: roles, permisos, grupos, asignaciones rol-permiso, usuario-rol, grupo-rol, ACL de recurso, auditoría de seguridad.
- **Workflow (0056)**: definiciones, pasos, reglas, instancias, tareas/aprobaciones, delegaciones, historial.
- **Comunicaciones (0057)**: notificaciones, mensajería, tareas, calendario, webhooks, plantillas.
- **BI/DW (0058)** y **BI Corporativo (0065)**: hechos/dimensiones, snapshots de KPI, `dw_hechos` unificado, cubos.
- **SaaS (0059)**: suscripciones/planes/uso, billing/dunning, usuarios multiempresa, branding.
- **Observabilidad/Seguridad (0060)**: incidentes/alertas, MFA TOTP, RGPD.
- **DR + CRM (0061)**: snapshots/drills DR; leads/oportunidades/actividades/scoring CRM.
- **MRP/Calidad (0062)**: BOM, centros, rutas, órdenes de fabricación; inspecciones, NC, CAPA, auditorías.
- **GMAO/SAT (0063)**: activos, planes preventivos, OT; tickets, SLA, KB.
- **Finanzas (0064)**: presupuestos/escenarios/versiones, préstamos/leasing, crédito/scoring.
- **Resiliencia (0066)**: outbox/inbox, event store, estado edge/sync.
- **Preferencias (0067)**: `preferencias_usuario`.

## 7. Nuevos servicios (agrupados por módulo)

**Paquetes (16):** `aeat/`, `bi/`, `bi_corp/`, `calidad/`, `crm/`, `dr/`, `finanzas/`, `gmao/`, `integraciones/`, `mrp/`, `observabilidad/`, `resiliencia/`, `saas/`, `sat/`, `seguridad/`, `workflow/`.

**Servicios transversales (8):** `autorizacion.py`, `calendario.py`, `mensajeria.py`, `notificaciones.py`, `plantillas_correo.py`, `scheduler.py`, `tareas.py`, `webhooks_salientes.py`.

**Capa de datos (3):** `db/rbac.py`, `db/workflow.py`, `db/preferencias.py`.

## 8. Nuevas interfaces / ventanas GUI (16)

`aeat_gui`, `seguridad_gui`, `workflow_gui`, `notificaciones_gui`, `bi_dashboard`, `bi_corporativo`, `saas_admin`, `crm_dashboard`, `dr_dashboard_gui`, `mrp_dashboard`, `calidad_dashboard`, `gmao_dashboard`, `sat_dashboard`, `finanzas_dashboard`, `resiliencia_dashboard`, `sidebar_colapsable` (componente global).

## 9. Integraciones entre módulos

- **Fabricación/GMAO/Resiliencia → Kárdex real**: órdenes de fabricación y consumo de repuestos usan los tipos `ENTRADA_PRODUCCION`/`SALIDA_PRODUCCION` y FEFO de lotes; el sync offline reinserta en el kárdex central de forma idempotente.
- **Finanzas → Tesorería**: la amortización de préstamos/leasing genera vencimientos AR/AP reales.
- **AEAT/Finanzas/BI → Contabilidad y Tesorería**: los calculadores BI reutilizan tesorería, contabilidad y AEAT como fuentes; BI Corporativo hace ETL desde los dominios de todos los módulos.
- **Workflow + RBAC + Auditoría**: el motor de aprobaciones se apoya en permisos RBAC y deja traza auditable.
- **SaaS enforcement**: planes cableados al menú y a los servicios (bloqueo por impago).
- **Comunicaciones**: notificaciones/webhooks disparados por eventos de los módulos.

## 10. Cambios de UX y TPV

- TPV con tarjetas **CLIENTES**, **Mostrar stock** (con permiso `stock.consultar_desde_tpv` + auditoría), **Venta online**, **Mov. efectivo** y **Cambio de cajero** (reutilizan ventanas/lógica existentes).
- **Gestión de Caja** extraída a ventana propia (`GestionCajaWindow`) y movida al menú; retirada como pestaña de Configuración.
- **Sidebar colapsable global** con persistencia por usuario (`preferencias_usuario`).
- **Responsive/multidispositivo**: High-DPI fluido (PassThrough), medidas fijas → min/max + size policy, mínimos tablet-friendly, alturas táctiles; fix del toggle Ocultar/Acciones; cierre de ventanas al volver al menú.

## 11. Cambios de seguridad

- RBAC/ACL completo + `autorizacion.puede()` con fallback legacy.
- MFA TOTP + códigos de recuperación; security headers; detección de anomalías; RGPD.
- `secret_manager` (backend Fernet; punto de extensión Vault/KMS) + `obtener_secreto()`.
- **Correo OAuth endurecido**: resolución del client por env (`GOOGLE_OAUTH_CLIENT_ID/SECRET`) → secret manager → fichero → `documentos/` (fallback), sin JSON en repo; tokens cifrados Fernet intactos.
- **Saneamiento del historial**: credencial OAuth real purgada con `git-filter-repo` (287 commits reescritos), auditada (0 referencias) y ya rotada en Google Cloud. `.gitignore` reforzado.

## 12. Cambios de resiliencia y continuidad operativa

- Offline-first: `offline_store` SQLite por tienda (espejo de catálogo + ventas/movimientos offline con hash-chain), cache manager, outbox/inbox, motor de sincronización idempotente.
- Event sourcing operativo (replay/snapshot), circuit breakers, watchdog/autoheal, edge node (online/degradado/offline/recuperación), chaos testing y RPO/RTO + dashboard.
- Disaster Recovery: PITR/snapshots, storage off-site, replicación, drills programados, runbook.

## 13. Cambios SaaS y multiempresa

- Planes BASIC/PLUS/PRO + `LicensingService` con enforcement real en menú y servicios; bloqueo por impago; billing webhook + dunning.
- Usuarios multiempresa, branding por tenant, backup/restore por tenant, métricas, Docker/gunicorn.
- Todo el modelo nuevo respeta el aislamiento por `id_empresa` (multiempresa) y por tienda.

## 14. Cambios BI y analítica

- Data Warehouse + motor de KPIs + calculadores por dominio + forecasting Prophet (degradable) + snapshots programados + comparativas multiempresa.
- BI Corporativo: `dw_hechos` unificado, ETL desde los dominios de todos los módulos, OLAP (cubos/drill/slice/dice), 23 KPIs corporativos, consolidación, alertas explicables, benchmarking, export multiformato e IA ejecutiva.

## 15. Cobertura de pruebas

- **43 nuevos ficheros de test** (integración por dominio: aeat, rbac, seguridad, observabilidad, workflow, comunicaciones, bi, saas, dr, crm, mrp, fabricación, calidad, gmao, sat, presupuestos, financiación, crédito, kpis, simulación, ia financiera, dw, olap, kpis corp, forecast, alertas, dashboards, offline_store, sync_engine, event_sourcing, circuit_breaker, watchdog, edge_node, chaos, rpo_rto, correo_oauth…).
- Escenarios cubiertos en cada bloque: alta/idempotencia, integración con kárdex/tesorería/contabilidad, RBAC, degradación sin dependencias opcionales y multiempresa.

## 16. Resultado final de la suite

```
879 passed · 3 deselected · 0 failed
```
(3 deselected = tests W3C XSD de Verifactu, flaky de entorno conocidos, ajenos a esta rama.)
Migraciones verificadas en BD vacía / con datos / upgrade. Arranque de ventanas clave: OK. Dashboards < 200 ms.

## 17. Riesgos residuales conocidos

- **Ficheros telemáticos AEAT oficiales** no generados (modelos calculados, sin envío telemático real).
- **Verifactu/TicketBAI**: re-sellado/live y eventos SIF posteriores fuera de alcance.
- **Backend OTel/Prometheus**: instrumentado y degradable, pero no validado contra un stack de observabilidad real desplegado.
- **Backend Vault/KMS**: `secret_manager` deja el punto de extensión; hoy degrada a entorno/Fernet.
- **3 tests XSD** dependientes de entorno (deseleccionados).
- **Empaquetado nativo** (macOS/iOS/Android) no abordado.

## 18. Deuda técnica pendiente

- Épica de **aislamiento multi-tenant** a nivel de `articulos`/operaciones (hoy MONO-EMPRESA por decisión registrada en `docs/tenancy.md`).
- Migrar el resto de credenciales/integraciones al patrón `secret_manager`.
- Consolidar manifiestos K8s reales (estructura preparada, no desplegada).
- Revisión visual responsive de algunos dashboards (ya 0 medidas fijas, pendiente QA manual).
- Normalización de saltos de línea (avisos CRLF/LF en Windows).

## 19. Completitud estimada por bloque (tras esta rama)

| Bloque | Estimación |
|---|---|
| Inventario / Kárdex / Lotes | ~95% |
| Compras / Aprovisionamiento | ~95% |
| Ventas / TPV / Facturación | ~92% |
| Fiscalidad (Verifactu/Facturae) | ~85% (falta telemático live) |
| AEAT (modelos) | ~85% (falta fichero oficial) |
| Contabilidad | ~85% |
| Tesorería / SEPA | ~90% |
| Finanzas avanzadas | ~85% |
| Seguridad / RBAC / MFA | ~90% |
| Observabilidad / DevOps | ~75% |
| Workflow / BPM | ~85% |
| Comunicaciones | ~85% |
| BI / BI Corporativo | ~85% |
| SaaS / Multiempresa | ~75% (pendiente aislamiento total) |
| DR / Resiliencia | ~80% |
| MRP / Calidad | ~80% |
| GMAO / SAT | ~80% |
| UX / Responsive | ~85% (pendiente empaquetado nativo) |

## 20. Completitud global estimada

**≈ 85% del alcance funcional objetivo** de Smart Manager AI tras esta rama (estimación cualitativa; la deuda principal es el aislamiento multi-tenant total y la presentación telemática oficial AEAT/Verifactu live).

## 21. Recomendaciones para la siguiente fase de desarrollo

1. **Aislamiento multi-tenant real** (`articulos`/operaciones por empresa) — habilitador de SaaS pleno.
2. **Presentación telemática oficial** AEAT + Verifactu/TicketBAI live (ficheros y firma en producción).
3. **Despliegue/observabilidad productivo**: manifiestos K8s + stack Prometheus/OTel validado + secret_manager con Vault/KMS.
4. **Endurecimiento financiero pre-banca** continuado y conciliación a escala.
5. **QA de dispositivo** (responsive end-to-end + empaquetado nativo).

## 22. Estado de fusión

### PR #1 — ya fusionado en `main` ✅

Fusionado mediante el commit de merge `271469c` (*Merge pull request #1 from
ogluzop-oss/feat/erp-enterprise-suite*; padres `1b42d51` + `c866b20`). Incorporó a `main`
los **14 primeros commits** de la rama, es decir, los bloques:

| Commit | Bloque incorporado a `main` |
|---|---|
| `024f750` | DevOps/CD (Docker, gunicorn/wsgi, CI build) |
| `60b6fc9` | Migraciones 0052–0067 |
| `47d326b` | Fiscalidad AEAT (303/390/111/190/347/349) |
| `f2a7724` | Seguridad/Observabilidad (RBAC/ACL, MFA TOTP, RGPD) |
| `d0c3008` | Workflow/BPM + Comunicaciones |
| `7e21790` | BI + SaaS |
| `65c021b` | Disaster Recovery + CRM |
| `316e81c` | MRP/Fabricación + Calidad |
| `670abdb` | GMAO + SAT/Helpdesk |
| `c4aae43` | Finanzas avanzadas + BI Corporativo |
| `f95ec3a` | Resiliencia / Offline-first |
| `8b11b64` | Ajustes Tesorería/Contabilidad (SEPA/posting) |
| `10b2e75` | UX-TPV-01 (TPV/navegación/responsive) |
| `2be830f`, `c866b20` | Higiene de repo (.gitignore: artefactos y credenciales) |

### PR #2 — ya fusionado en `main` ✅

Fusionado mediante el commit de merge `2989fef` (*Merge pull request #2 from
ogluzop-oss/feat/erp-enterprise-suite*). Incorporó a `main`:

- `32b73e0` — endurecimiento OAuth / Secret Manager (correo corporativo).
- `84c13b4` — `PULL_REQUEST.md` (documentación del PR).

### Estado consolidado

- ✅ **Todo el trabajo funcional de la rama está en `main`** (bloques de PR #1 + endurecimiento OAuth de PR #2).
- ✅ **Merge limpio verificado** (`git merge-tree`, sin conflictos).
- ⚠️ **No fast-forward:** ambos merges generaron commit de merge (`271469c`, `2989fef`).
- ✅ **Secretos:** 0 referencias a credenciales en el historial de la rama y en `main`
  (secreto purgado y rotado).
- ✅ **Esquema:** 100% aditivo (`IF NOT EXISTS`) — no rompe instalaciones con datos.
- 🔁 **Pendiente (no funcional):** sincronizar esta documentación con `main` mediante un PR de
  docs, o cerrar la rama si no se necesita conservarla.

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
