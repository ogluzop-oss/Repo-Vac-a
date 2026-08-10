# Informe Final — Recuperación e Integración de Funcionalidades Enterprise

**Fecha:** 2026-07-06 · **Alcance:** integración de trabajo ya existente (no desarrollo nuevo) ·
**Invariantes respetadas:** SOMA, Plan UI Enterprise, Mission Engine, Workflow, Gobierno, Autonomía y
la arquitectura de navegación aprobada — **intactos**. Reutilización estricta; sin ventanas nuevas ni
lógica duplicada. Verificación: AST + instanciación offscreen + render visual + smoke `5 passed` tras
cada bloque.

## 1. Tareas completadas

| # | Bloque | Resultado |
|---|---|---|
| 0 | Auditoría de navegación | `INFORME_AUDITORIA_NAVEGACION.md` (previo, aprobado) |
| 1 | **Dashboards Enterprise** (prioridad máxima) | 9 dashboards huérfanos recuperados por afinidad funcional (ver §4) |
| 2 | **TPV** | Autocobro integrado (botón + `_abrir_autocobro` + salida con Esc); báscula/devoluciones/granel ya estaban correctamente integrados |
| 3 | **Jobs Enterprise** | Registro selectivo de 5 familias seguras + wire del registro al arranque (sin ejecutar) |
| 4 | **Combo global** | Overrides inline eliminados en `recepcion_pale.py` → flecha unificada |
| 5 | **MFA/TOTP** | Reto de segundo factor cableado en el login (servicio sin tocar) |
| 6 | **Comunicaciones** | Auditoría: arquitectura correctamente preparada (nada que desarrollar) |
| 7 | **Fiscalidad** | Estado verificado y documentado (§7) |
| 8 | **Responsive P2** | 3 pantallas corregidas; 3 ya responsive (sin cambios) |
| 9 | **Multitenant** | Auditoría: mono-empresa, sin acción; integraciones no rompen el futuro |

## 2. Incidencias detectadas

- **9 dashboards Enterprise huérfanos** (0 referencias en `src/`): backend+migración+GUI construidos pero inalcanzables. → Resuelto.
- **Autocobro sin entrada desde el TPV**: existía como ventana/terminal independiente sin botón. → Resuelto.
- **Scheduler nunca arrancado**: ni `registrar_jobs_por_defecto()` ni `ejecutar_pendientes()` se invocaban en el arranque; ningún job programado corría (solo SOMA por su latido). → Registro cableado al arranque.
- **`registrar_job` deja `proxima_ejecucion = NULL`** → todo job recién registrado queda "vencido"; ejecutar pendientes al arranque dispararía TODO a la vez (backup, snapshots…). → Decisión: no auto-ejecutar (evitar carga).
- **MFA sin cablear en el login** y **sin UI de alta (enrollment)**. → Reto en login resuelto; enrollment diferido.
- **Ancho mínimo excesivo** en `mostrar_stock` (1746 px), `tpv` (1546 px) y `ubicacion_tienda` (1393 px), heredado de contenido/ventanas embebidas → no cabían en portátiles de 1366 px. → Resuelto.

## 3. Decisiones arquitectónicas

- **Dashboards por afinidad funcional, sin tarjetas/hubs nuevos**: cada dominio donde el usuario lo espera. Se convirtió `AlmacenesWindow` en anfitriona con pestañas (permitido) y se reutilizó el patrón sidebar+stack de Compras para Calidad. CRM pasa a ser la entrada del dominio Clientes.
- **Jobs**: solo se auto-registran los ligeros/valiosos y sin dependencias externas (SLA SAT, preventivo GMAO, automatización CRM, snapshots BI, ratios financieros). Los pesados/condicionados quedan **opt-in**. La **ejecución** de pendientes NO se auto-invoca (no hay daemon; se evita carga en el arranque).
- **MFA**: reto en el login (3 intentos, código TOTP **o** de recuperación), reutilizando `services.seguridad.mfa` sin modificarlo; no intrusivo (usuarios sin MFA entran igual).
- **Responsive**: criterio empírico — solo se interviene si el ancho mínimo supera ~1366 px (no cabe en portátil pequeño); el resto se deja intacto. La corrección es un **scroll-wrap** del área de contenido (no altera proporciones ni el diseño Enterprise).
- **Combo**: los `_NeonComboBox` (gestion_usuarios/ventas) que **pintan su propia** flecha se conservan; solo se eliminan los overrides que **ocultaban** la flecha global.

## 4. Dashboards recuperados — ubicación definitiva

| Dashboard | Dominio | Ubicación (reutilizando su acceso) |
|---|---|---|
| CRM Comercial | Clientes/Comercial | Tarjeta "Clientes" → `CRMDashboardWindow` (entrada); pestañas *Clientes* (`clientes_gui`) y *SAT/Postventa* |
| SAT / Helpdesk | Postventa | Pestaña en el hub CRM |
| Calidad | Suministro/recepción | Sección "Calidad" en Compras/Proveedores |
| MRP / Fabricación | Operaciones/producción | Pestaña en Almacenes (convertida a anfitriona) |
| GMAO / Mantenimiento | Activos | Pestaña en Almacenes |
| Finanzas Avanzadas | Financiero | Pestaña en Tesorería |
| DR + Resiliencia | Infra/continuidad | Pestañas en Seguridad |
| BI Corporativo | Inteligencia | Pestaña (lazy) en Centro de Inteligencia |

Verificado: las 9 clases pasan de 0 → 1 referencia (ninguna huérfana).

## 5. Jobs — activos vs opt-in

**Auto-registrados** (en `scheduler.registrar_jobs_por_defecto`, cableado al arranque, sin ejecutar):
vencimientos (24 h), workflow_sla (12 h), backup (24 h), DR drills, gemelo consistencia · **+ nuevos:**
`sat_sla` (4 h), `gmao_preventivo` (24 h), `crm_automatizacion` (24 h), snapshots BI (diario/…),
finanzas (ratios/riesgo/anomalías, 24 h).

**Opt-in deliberado** (no auto-registrados, por carga o dependencias): `bi_corp_etl` (ETL DW pesado),
`bi_corp_alertas` (depende del ETL), `resiliencia_sync`/`watchdog`/`cache_warmup` (escenario
edge/offline), `sat_email_ticket` (requiere IMAP), `SAAS_DUNNING` (solo instalaciones SaaS).

## 6. Responsive P2 — por pantalla

| Pantalla | Ancho mínimo (antes → después) | Acción |
|---|---|---|
| mostrar_stock | 1746 → **398** | scroll-wrap del contenido (QStackedWidget con ventanas embebidas) |
| tpv | 1546 → **90** | scroll-wrap del stack principal |
| ubicacion_tienda | 1393 → **398** | scroll-wrap del área de vistas |
| gestion_usuarios (Configuración) | **1158** | sin cambios (ya cabe en 1366 px) |
| recepcion_pale | **646** | sin cambios |
| ventas | **954** | sin cambios |

Las medidas fijas restantes (alturas de inputs/botones 34-55 px, ilustraciones 200 px, sidebar 280 px,
etiquetas de formulario 130 px) se conservan por tener justificación funcional/visual y ser escaladas
por Qt en DPI (100-200 %). Validado con render offscreen a 1000-1200 px (contenido íntegro + scrollbar
turquesa; diseño Enterprise intacto).

## 7. Auditorías (sin desarrollo, por instrucción)

- **Comunicaciones**: framework `integraciones.enviar()` correctamente preparado. Webhooks
  Slack/Telegram/Teams **operativos**; correo con modos `simulado`/`google` (real vía Gmail OAuth
  cifrado)/`smtp` (reservado). MS Graph/Outlook/Exchange, Google Calendar, DocuSign/Adobe Sign →
  declarados como `credenciales`, degradan a `no_configurado` sin romper. **Nada que desarrollar**;
  la arquitectura ya está lista para activar con SDK+credenciales.
- **Fiscalidad**: **implementado** — Verifactu (conforme XSD/WSDL, certificados/mTLS/XAdES), Facturae
  (FACe/DIR3) y modelos AEAT 303/390/111/190/347/349. **Diferido para certificación real**: re-sellado
  XSD/WSDL oficiales *live*, PDFs Facturae (huella/QR/política de firma), certificado de producción,
  round-trip *live* (Verifactu preproducción + FACe), fichero telemático oficial AEAT. **Épicas
  posteriores por decisión (no implementar):** TicketBAI (foral) y Eventos SIF.
- **Multitenant**: infra lista (`empresa_actual_id()`/contexto/`EMPRESA_DEFAULT_ID`), escenario
  **mono-empresa por decisión**. Las integraciones de este bloque respetan el contexto de empresa
  (los dashboards embebidos usan `_emp()`/`id_empresa`), por lo que **no rompen** el multitenant
  futuro. Aislamiento real por consulta (3b/3c) sigue diferido: sin valor en mono-empresa, añade riesgo.

## 8. Elementos deliberadamente diferidos para futuras versiones

1. **Ejecución automática de jobs** del Scheduler (hoy solo se registran; no hay daemon — se evita
   carga en el arranque). Recomendado: disparador controlado ("ejecutar ahora" en un panel de jobs, o
   tick de fondo en reposo).
2. **UI de alta de MFA** (activar 2FA + mostrar QR/secreto + generar códigos de recuperación desde
   perfil/seguridad). El servicio y el reto de login ya están listos.
3. **Jobs Enterprise opt-in** (§5).
4. **Comunicaciones reales** (MS Graph/Google Calendar/DocuSign): SDK + credenciales.
5. **Fiscalidad**: TicketBAI, Eventos SIF, y los pendientes externos de certificación (§7).
6. **Multitenant 3b/3c** (aislamiento real por consulta) — cuando el escenario deje de ser mono-empresa.

## 9. Verificación global

- AST OK en todos los ficheros modificados.
- Instanciación offscreen de todas las ventanas anfitrionas y de los 9 dashboards embebidos: OK.
- Render visual de pantallas responsive a 1000-1200 px: contenido íntegro, sin recortes.
- `smoke_test.py`: **5 passed** tras cada bloque y al cierre.
- SOMA, Plan UI Enterprise y navegación aprobada: **sin cambios**.
