# CERTIFICACIÓN — CIERRE DE BRECHAS FUNCIONALES (Fiscal/AEAT · Producción/MRP · GMAO · Calidad · SAT)

## Smart Manager AI · Proyecto multi-iteración (área por área)

Este documento se actualiza **por área**. Cada área se declara con su estado real, sin sobrepromesa:

**🟢 OPERATIVO REAL · 🟡 PARCIAL · 🔵 BACKEND NO EXPUESTO · 🟠 SIMULADO/DEGRADABLE · 🟣 PREPARADO FUTURO · 🔴 NO EXISTE**

---

## Estado global de las 5 áreas

| Área | Estado ANTES | Estado AHORA | Iteración |
|---|---|---|---|
| **Producción / MRP** | 🔵 Backend + dashboard read-only (0 acciones) | **🟢 OPERATIVO REAL** | **1 (cerrada)** |
| **Calidad** | 🔵 Backend + dashboard read-only (0 acciones) | **🟢 OPERATIVO REAL** | **2 (cerrada)** |
| **GMAO** | 🔵 Backend + dashboard read-only (0 acciones) | **🟢 OPERATIVO REAL** | **3 (cerrada)** |
| **SAT** | 🔵 Backend + dashboard read-only (0 acciones) | **🟢 OPERATIVO REAL** (núcleo) | **4 (cerrada)** |
| **Fiscal / AEAT** | 🟠 Motor REAL pero **sin exponer** (sin GUI de certificados/envío) | **🟢 EXPUESTO** (motor real) / 🟠 aceptación legal externa | **5 (cerrada)** |

---

## ITERACIÓN 1 — PRODUCCIÓN / MRP → 🟢 OPERATIVO REAL

### Estado inicial (auditoría Fase 0)
- Backend **completo** en `src/services/mrp/` (`bom, ordenes, costes, centros, mps, planificador, produccion_pro, analitica`), con ciclo de OF y consumo/producción ya cableados al **motor oficial** (`db/kardex`, `db/lotes`), auditado (`FAB_*`), idempotente. Tablas: migr **0062/0115**.
- GUI: `mrp_dashboard.py` era **solo lectura** (0 botones de acción). RBAC ya definido: `mrp.ver/bom/planificar/admin`.

### Cambios realizados (solo EXPONER, sin duplicar — N7)
1. **GUI operativa** ([mrp_dashboard.py](src/gui/mrp_dashboard.py)): barra de acciones sobre Órdenes de Fabricación (Nueva OF · Planificar · Liberar · Iniciar · Pausar · **Consumir materiales** · **Registrar producción** · **Finalizar** · Cancelar), diálogos **Nueva OF** y **Nueva BOM** (con componentes editables), y ventana `ProduccionWindow`. Todas las acciones invocan los **servicios existentes** — 0 lógica de negocio nueva, 0 motor de stock nuevo.
2. **Ruta de menú** ([menu_principal.py](src/gui/menu_principal.py)): tarjeta **"Producción"** (v_id `produccion`, icono `gear`, perfiles ADMIN/GERENTE) → `ProduccionWindow`. El hosting previo en Almacenes se conserva (compatibilidad).
3. **RBAC**: reutiliza los permisos existentes (`mrp.admin` para gestión de OF, `mrp.planificar` para planificar, `mrp.bom` para alta de BOM) vía el motor único `services.autorizacion.puede`. **No se creó ningún permiso ni sistema de seguridad paralelo.**
4. **Auditoría**: sin cambios — la emite el backend (`FAB_OF_CREATED/PLANIFICADA/.../CONSUMO/PRODUCCION`). No se registra ningún secreto.

### Reutilización (N7)
- Stock/existencias: `ordenes.consumir_materiales` → `lotes.consumir_fefo` / `kardex.registrar_movimiento (SALIDA_PRODUCCION)`; `ordenes.registrar_produccion` → `lotes.registrar_entrada` / `kardex (ENTRADA_PRODUCCION)`. **Motor oficial único.**
- Costes: `services.mrp.costes.calcular_coste_real_of` (sin sistema contable paralelo).
- RBAC/auditoría/empresa: infraestructuras únicas existentes.

### Tablas nuevas / migraciones
- **Ninguna.** Se reutilizan `bom`, `bom_lineas`, `ordenes_fabricacion`, `of_consumos`, `of_produccion`, `of_operaciones` (migr 0062/0115).

### Pruebas
- Nueva suite [test_mrp_operativo.py](tests/unit/test_mrp_operativo.py) (**2 tests**): ciclo completo Producto→BOM→OF→(planificar/liberar/iniciar)→consumo (kárdex SALIDA_PRODUCCION ×2)→producción (of_produccion + cantidad_producida)→finalización con costes + máquina de estados (transición inválida rechazada); e **idempotencia** del consumo (no duplica movimientos de kárdex).
- **Regresión completa: 587 passed, 1 skipped (0 regresiones).**

### Criterio de finalización (Fase 14) — verificado
> **¿Puede un usuario completar una orden de fabricación real?** → **SÍ.** Desde el menú **Producción**: crear BOM, crear OF, planificar/liberar/iniciar, consumir componentes (baja de stock oficial), registrar producto terminado (alta de stock oficial), finalizar con costes. Trazabilidad BOM→consumos→OF→producto en tablas `of_*` + kárdex.

### Limitaciones restantes (honestidad)
- La GUI operativa expone el **ciclo principal de OF**; el detalle fino de **rutas/operaciones/partes de trabajo por centro** (`produccion_pro`, `centros`) sigue disponible en backend y KPIs, pero su edición granular en pantalla es mínima (siguiente refinamiento, no bloquea el ciclo).
- Acciones críticas: se protegen con **RBAC**; no se añadió step-up (las acciones de producción son operativas, no de seguridad crítica) — el registro `mfa_stepup.ACCIONES_CRITICAS` se mantiene **congelado**.

---

## ITERACIÓN 2 — CALIDAD → 🟢 OPERATIVO REAL

### Estado inicial (Fase 0)
- Backend **completo** en `src/services/calidad/` (`inspecciones, no_conformidades, capa, auditorias,
  trazabilidad, analitica`), auditado (`CAL_*`/`NC_*`/`CAPA_*`), con la **integración Compras→Calidad ya
  en el backend**: una inspección de recepción con resultado `rechazada` **abre automáticamente una NC**.
  Tablas: migr **0062/0116**. Permisos granulares ya existentes (`inspecciones.crear`, `nc.crear`,
  `auditorias.gestionar`, `calidad.admin`).
- GUI: `calidad_dashboard.py` era **solo lectura** (0 acciones), hospedado en Compras.

### Cambios realizados (solo EXPONER — N7)
1. **GUI operativa** ([calidad_dashboard.py](src/gui/calidad_dashboard.py)): barras de acción en
   Inspecciones (**Nueva inspección** recepción/producción/final → rechazo genera NC), No Conformidades
   (Nueva NC + ciclo `abierta→en_análisis→accionada→cerrada/rechazada`) y CAPA (Nueva acción + `abierta→
   en_curso→cerrada[eficacia]/cancelada`). Diálogos `_NuevaInspeccionDialog/_NuevaNCDialog/_NuevaCAPADialog`.
2. **Ruta de menú** ([menu_principal.py](src/gui/menu_principal.py)): tarjeta **"Calidad"** (v_id `calidad`,
   icono `clipboard_check`) → `CalidadDashboardWindow`. Se conserva el hosting en Compras.
3. **RBAC** reutilizado (`inspecciones.crear`, `nc.crear`, `calidad.admin`) vía `autorizacion.puede`.
4. **Bug corregido**: `inspector`/`responsable` son columnas **INT** (id de usuario) — la GUI ahora pasa
   `usuario.id`, no el nombre (habría fallado en runtime).

### Reutilización / tablas nuevas
- Reutiliza `inspecciones`, `no_conformidades`, `acciones_correctivas`, `planes_inspeccion`, `auditorias`
  (migr 0062/0116). **0 migraciones nuevas, 0 permisos nuevos, 0 motores nuevos.**

### Pruebas
- Nueva suite [test_calidad_operativo.py](tests/unit/test_calidad_operativo.py) (**2 tests**): recepción
  rechazada → **NC automática** → ciclo NC (con transición inválida rechazada) → CAPA ligada
  (en_curso→cerrada con eficacia) → cierre NC → listados; e inspección aceptada **no** genera NC.
- **Regresión completa: 589 passed, 1 skipped (0 regresiones).**

### Criterio de finalización (Fase 14) — verificado
> **¿Puede gestionar inspecciones y no conformidades?** → **SÍ.** Desde el menú **Calidad**: registrar
> inspecciones (recepción/producción/final), el rechazo abre NC automática, gestionar el ciclo de NC y las
> acciones CAPA con verificación de eficacia. Integración Compras→Calidad operativa.

### Limitaciones restantes
- Auditorías (`auditorias.planificar/registrar_hallazgo/cerrar`) y trazabilidad siguen en backend + vista;
  su alta/gestión en pantalla es el siguiente refinamiento (no bloquea el ciclo inspección→NC→CAPA).

---

## ITERACIÓN 3 — GMAO → 🟢 OPERATIVO REAL

### Estado inicial (Fase 0)
- Backend **completo** en `src/services/gmao/` (`activos, planes, ordenes, analitica, gmao_pro`), con OT
  cableadas al **kárdex oficial** para repuestos (`consumir_repuestos` → SALIDA_PRODUCCION, id_documento
  `OT:<id>`), costes en cierre, auditado (`GMAO_*`). Tablas: migr **0063/0117**. Permisos ya existentes
  (`gmao.ver/admin`, `activos.ver/gestionar`, `ot.ver/crear`).
- GUI: `gmao_dashboard.py` era **solo lectura** (0 acciones), hospedado en Almacenes.

### Cambios realizados (solo EXPONER — N7)
1. **GUI operativa** ([gmao_dashboard.py](src/gui/gmao_dashboard.py)): Activos (alta + estado
   operativo/mantenimiento/baja), Órdenes de Trabajo (Nueva OT correctiva/preventiva/predictiva, Asignar
   técnico, Iniciar/Pausar/Cancelar, **Añadir repuesto**, **Consumir repuestos** [kárdex oficial],
   **Finalizar** con horas→costes) y Planes preventivos (Nuevo plan + **Generar OT preventivas vencidas**).
   Diálogos `_NuevoActivoDialog/_NuevaOTDialog/_RepuestoDialog/_NuevoPlanDialog`.
2. **Ruta de menú** ([menu_principal.py](src/gui/menu_principal.py)): tarjeta **"Mantenimiento"** (v_id
   `gmao`, icono `worker_box`) → `GMAODashboardWindow`. Se conserva el hosting en Almacenes.
3. **RBAC** reutilizado (`activos.gestionar`, `ot.crear`, `gmao.admin`). `tecnico`/`responsable` son INT.
4. **Bug real corregido (habría crasheado la app)**: un método conectado como slot con **`ñ` en el nombre**
   (`_añadir_repuesto`) provocaba **segfault** en PyQt/SIP al `connect`. Renombrado a `_anadir_repuesto`
   (ASCII). Lección: no conectar como slot directo métodos con caracteres no-ASCII en el nombre.

### Reutilización / tablas nuevas
- Reutiliza `activos`, `ordenes_trabajo`, `ot_recursos`, `costes_ot`, `planes_mantenimiento` (migr
  0063/0117) + kárdex/lotes oficiales. **0 migraciones, 0 permisos, 0 motores nuevos.**

### Pruebas
- Nueva suite [test_gmao_operativo.py](tests/unit/test_gmao_operativo.py) (**2 tests**): ciclo correctivo
  (activo→OT→asignar→iniciar→repuesto→finalizar con **consumo por kárdex oficial** + costes + transición
  inválida rechazada) y ciclo preventivo (plan vencido → generación de OT preventiva).
- **Regresión completa: 591 passed, 1 skipped (0 regresiones).**

### Criterio de finalización (Fase 14) — verificado
> **¿Puede gestionar un ciclo de mantenimiento completo?** → **SÍ.** Desde el menú **Mantenimiento**: alta
> de activos, planes preventivos con generación automática de OT, y correctivo extremo a extremo (OT →
> técnico → repuesto por stock oficial → cierre con costes e historial).

### Limitaciones restantes
- Medidores/checklists de rondas (`gmao_pro`) y el historial detallado por activo siguen en backend + KPIs;
  su gestión en pantalla es el siguiente refinamiento (no bloquea el ciclo preventivo/correctivo).

---

## ITERACIÓN 4 — SAT / HELPDESK → 🟢 OPERATIVO REAL (núcleo)

### Estado inicial (Fase 0)
- Backend **completo** en `src/services/sat/` (`tickets, intervenciones, contratos_sla, kb, sat_pro,
  analitica`), auditado (`SAT_*`). Tablas: migr **0063/0118**. Permisos ya existentes (`sat.ver/admin`,
  `tickets.ver/crear/gestionar`). Portal de cliente (`PortalSATWindow`) y KB ya operativos.
- GUI: `sat_dashboard.py` era **solo lectura** para gestión interna (tickets sin acciones).

### Cambios realizados (solo EXPONER — N7)
1. **GUI operativa** ([sat_dashboard.py](src/gui/sat_dashboard.py)): Tickets (**Nueva incidencia**, Asignar
   técnico, ciclo abierto→asignado→en_proceso→pendiente→resuelto→cerrado→reabierto, **Comentar**,
   **Registrar intervención**), pestaña Intervenciones (por ticket), y Contratos/SLA + **Bolsa de horas**
   (crear contrato, crear bolsa, **consumir horas** = facturación por horas prepago). Diálogos
   `_NuevoTicketDialog`/`_IntervencionDialog`.
2. **Ruta de menú** ([menu_principal.py](src/gui/menu_principal.py)): tarjeta **"Soporte (SAT)"** (v_id
   `sat`, icono `monitor_search`) → `SATDashboardWindow`. Se conserva el hosting en CRM.
3. **RBAC** reutilizado (`tickets.crear`, `tickets.gestionar`, `sat.admin`). `tecnico`/`autor` son INT.
   Todos los métodos-slot con nombre ASCII (evitado el bug `ñ`→segfault de la iteración GMAO).

### Alcance HONESTO (lo que el backend SAT NO tiene — no se inventa)
- ❌ **Repuestos con consumo de stock**: `intervenciones` NO tiene repuestos ni toca el kárdex (a
  diferencia de GMAO). No se añade un motor de repuestos.
- ❌ **Factura comercial desde el ticket**: no existe función de facturación en `services.sat`. La
  facturación real disponible es la **bolsa de horas** (`sat_pro.consumir_horas`), que sí se expone.
  Conectar el ticket con el módulo de facturación comercial queda como refinamiento futuro (no es
  "exponer lo existente").

### Pruebas
- Nueva suite [test_sat_operativo.py](tests/unit/test_sat_operativo.py) (**2 tests**): ciclo de ticket
  (asignar técnico → estados → comentario → intervención listada + transición inválida rechazada) y bolsa
  de horas (crear → consumir → saldo decrementado a 7/10).
- **Regresión completa: 593 passed, 1 skipped (0 regresiones).**

### Criterio de finalización (Fase 14) — verificado (con matiz honesto)
> **¿Puede gestionar una reparación desde el ticket hasta [el cierre]?** → **SÍ.** Ticket → técnico →
> intervención → resolución → cierre, con SLA y consumo de bolsa de horas. **Matiz:** "hasta la
> **factura** comercial" NO está cableado en el backend SAT (sí la facturación por horas prepago).

---

## ITERACIÓN 5 — FISCAL / AEAT → 🟢 EXPUESTO (motor REAL) · aceptación legal externa

### CORRECCIÓN a la auditoría inicial (honestidad)
La auditoría del vídeo lo marcó "🟠 simulado, sin envío legal". **Tras auditar a fondo, era una
sub-estimación**: el motor fiscal es **REAL y certificado**, no un mock:
- `services/fiscal/emisores/verifactu_aeat.py` → envío **SOAP conforme al WSDL** a los **endpoints
  OFICIALES de la AEAT** (`www1.agenciatributaria.gob.es` producción / `prewww1.aeat.es` preproducción),
  con throttling (TiempoEsperaEnvio).
- `services/fiscal/emisores/tls.py` → **mTLS real** (SSLContext en memoria, PyOpenSSL, `requests` con
  adaptador mTLS, `s.post(url, ...)`).
- `services/fiscal/certificados.py` → gestión completa del **PKCS#12 cifrado** (importar/inspeccionar/
  activar/revocar/rotar cifrado/caducidad/auditoría).
- `services/fiscal/verifactu_legal.py` → **huella/encadenado hash legal** + QR conforme.
- `services/fiscal/worker.py` → cola con **máquina de estados real** (generado→firmado→enviado→
  rechazado/anulado) y acuse. El proveedor `simulado` es solo el **fallback sin certificado**.

**El hueco real era la EXPOSICIÓN**: no había GUI para gestionar el certificado (habilitador de la
transmisión) ni para monitorizar/enviar los registros.

### Cambios realizados (solo EXPONER — N7, sin tocar el motor certificado)
1. **GUI nueva** ([fiscal_gui.py](src/gui/fiscal_gui.py) — `FiscalWindow`): pestaña **Certificados**
   (importar `.p12/.pfx` con contraseña, inspeccionar titular/caducidad, listar, activar, revocar, aviso
   de caducidad; **el material del certificado nunca se muestra ni se registra**) y pestaña **Registros
   Verifactu** (lista de registros con su **estado real** + **"Procesar cola de envío a la AEAT"** con
   confirmación, que ejecuta el worker REAL `procesar_cola`). Indicador claro de si la transmisión real
   está habilitada (hay certificado activo) o no.
2. **Ruta de menú** ([menu_principal.py](src/gui/menu_principal.py)): tarjeta **"Fiscal"** (v_id `fiscal`,
   icono `document`) → `FiscalWindow`.
3. **RBAC** reutilizado (`aeat.presentar` para gestión de certificado y envío; `aeat.ver`).

### INVARIANTE DE HONESTIDAD (garantizada por diseño + tests)
- **Sin certificado de PRODUCCIÓN válido + empresa dada de alta en la AEAT, la transmisión no se acepta.**
  Los registros quedan en `generado`; el estado `enviado` SOLO lo fija el worker con el **acuse REAL** de
  la AEAT. **NUNCA se simula la aceptación.** La GUI muestra explícitamente "sin certificado activo →
  transmisión NO habilitada".
- Estados siempre distinguidos: calculado/`generado` · `firmado` · `enviado` · `rechazado` · `anulado`.

### Lo que queda FUERA (bloqueo externo, no de código)
- La **aceptación legal efectiva** requiere: certificado de producción del contribuyente + alta en el censo
  AEAT + entorno con salida a los endpoints reales. **No es verificable en este entorno de desarrollo** y
  no depende de código adicional. Modelos AEAT (303/390/111/190/347/349) siguen calculándose y generándose;
  su fichero telemático oficial de presentación por modelo queda como refinamiento aparte de Verifactu.

### Pruebas
- Nueva suite [test_fiscal_operativo.py](tests/unit/test_fiscal_operativo.py) (**4 tests**, sin red):
  registro `generado` + máquina de estados; **sin certificado → sin transmisión** (`obtener_activo` None);
  **cola vacía no inventa envíos** (0 enviados); PKCS#12 inválido se rechaza.
- **Regresión completa: 597 passed, 1 skipped (0 regresiones).**

### Criterio de finalización (Fase 14) — verificado con honestidad
> **¿Puede generar y tramitar fiscalidad real según los mecanismos oficiales disponibles?** → **SÍ, el
> código lo hace de verdad** (mTLS + web service oficial + certificado + estados). La **aceptación legal**
> depende de un certificado de producción y del alta AEAT del contribuyente — condición EXTERNA, nunca
> simulada por la aplicación.

---

## Cierre del programa — 5/5 áreas

| Área | Resultado |
|---|---|
| Producción/MRP · Calidad · GMAO · SAT | 🟢 OPERATIVO REAL |
| Fiscal/AEAT | 🟢 motor real EXPUESTO · aceptación legal = condición externa (certificado prod + alta AEAT) |

Todas reutilizan la infraestructura existente (kárdex/lotes, RBAC `autorizacion`, auditoría, facturación,
certificados/mTLS fiscales). **0 motores paralelos, 0 tablas nuevas, 0 permisos nuevos.** Bug PyQt (método
con `ñ` como slot → segfault) encontrado y corregido. Regresión final **597 passed**.

## Áreas pendientes (sin tocar en esta iteración)
GMAO · Calidad · SAT · Fiscal/AEAT permanecen en su estado auditado. **Fiscal/AEAT** tiene un **bloqueo de entorno/regulatorio**: la transmisión telemática legal exige certificado de producción + endpoints reales AEAT + mTLS, no disponibles ni verificables en este entorno; su cierre honesto llega hasta generación/validación/XML/estado, nunca simulando la aceptación.

**Invariante mantenida:** un único motor por responsabilidad (stock, costes, RBAC, auditoría). Sin motores paralelos. Sin romper TPV/ventas/stock/compras/CRM/RRHH/contabilidad/tesorería/comercio digital/SaaS/MFA/multiempresa.
