# INFORME — Corporate Communication Platform (CCP) · FASE II

**Proyecto:** Smart Manager AI · **Bloque:** CCP Fase II (consolidación como núcleo único de
comunicaciones) · **Estado:** implementado y validado · **Fecha:** 2026-07-12

---

## 1. Arquitectura implementada

Sobre la CCP existente se han construido 10 capas (B1–B10), TODAS como **servicios API-First** en
`src/services/ccp/*` **sin PyQt** (lógica desacoplada, reutilizable desde REST/móvil/portal/IA). La GUI
solo consume. Ningún módulo se comunica con los canales directamente: todo pasa por el Corporate
Communication Service; toda resolución por el Corporate Identity Resolver; toda comunicación tiene
Communication ID.

```
Corporate Communication Service (enviar_comunicacion)
  → com_id → Identity Resolver → Channel Policy → [Gobierno B10] → Canal → Conversation B4
  → historial + auditoría + eventos + telemetría
Capas Fase II: Templates(B1) · Workflows(B2) · Campañas+Cola(B3) · Timeline+Conversation(B4) ·
  Analytics(B5) · Notification Center(B6) · Contacts CRM(B7) · Omnichannel(B8) · IA(B9) · Governance(B10)
```

## 2. Componentes nuevos

| Bloque | Módulo (servicio) | Función |
|---|---|---|
| B1 Templates Manager | `ccp/templates.py` | Plantillas con categorías/idiomas, **versionado + comparación**, estados (borrador/producción/archivada), formatos (texto/HTML/Markdown), render con variables/decoradores, import/export. |
| B2 Workflow Engine | `ccp/workflows.py` | Flujos de comunicación reutilizables (pasos enviar/esperar/condición/notificar/incidencia) ejecutados sobre la CCP; semilla `factura_pendiente`. |
| B3 Campaign Manager | `ccp/campanas.py` + `ccp/cola.py` (`ColaBD`) | Campañas (crear/programar/pausar/reanudar/cancelar/estadísticas) despachadas por la **Outgoing Queue real** (`ccp_cola`) vía el Communication Service. |
| B4 Timeline + Conversation | `ccp/timeline.py` + `ccp/conversaciones.py` | Cronología ÚNICA (todos los canales + entrantes) y **Conversation** (hilos, `conversation_id`). |
| B5 Analytics | `ccp/analitica.py` | KPIs (por canal/estado/contexto/usuario, enviados/fallidos/reintentos/cola/tasa éxito) + telemetría. |
| B6 Notification Center | `ccp/notificaciones_centro.py` | Centro único: internas (`services.notificaciones`) + externas (Communication Service). Sin segundo sistema. |
| B7 Contacts CRM | `ccp/contactos_crm.py` | Relaciones/jerarquías (empresa→…→persona), responsables/sustitutos, árbol (`ccp_relaciones`). |
| B8 Omnichannel | `ccp/canales/omnichannel.py` | WhatsApp/SMS/Push/Teams/Slack/Telegram/Firma como `CanalComunicacion` **degradables** (reales si hay credenciales; si no, `no_operativo`). |
| B9 IA Assistant | `ccp/ia_asistente.py` | Redactar/responder/traducir/corregir/resumir/tono/asunto/clasificar/extraer, **degradable** sobre la IA existente. Nunca toca el motor de correo. |
| B10 Governance | `ccp/gobierno_comunicaciones.py` | RGPD/consentimientos + políticas (listas negras/blancas, canales prohibidos, retención) aplicadas en el **pipeline** del servicio, asociadas al com_id. |

GUI mínima: `src/gui/ccp_panel.py` (Analítica/Timeline/Campañas) — solo consume servicios. Botón "CCP"
en el módulo de Correo.

Migraciones (aditivas, reversibles): `0125_ccp_plantillas`, `0126_ccp_campanas`,
`0127_ccp_conversaciones` (+`conversation_id`), `0128_ccp_crm`, `0129_ccp_gobierno`.

## 3. Componentes reutilizados (no reescritos)

CCP Fase I completa (servicio/identidad/organizacion/motor/canales/plantillas/telemetría/Communication
ID) · `plantillas_correo` · `services.notificaciones` · `services.workflow` · `bi/calculadores` +
`observabilidad/metricas` (Prometheus) + `observabilidad/tracing` (OTel) · `identidad/gobierno` +
organigrama · RBAC · Event Bus · `correo.enviar_documento` (motor de envío, INTACTO).

## 4. Diagrama de relaciones (resumen)

```
Módulo ─→ ccp.enviar_comunicacion ─→ Identity Resolver ─→ (destinatario)
                                   ─→ Channel Policy ─→ Canal (email real / omnichannel degradable)
                                   ─→ Gobierno (B10) [permite/bloquea]
                                   ─→ Conversation (B4)  ─→ Timeline (B4)
                                   ─→ ccp_comunicaciones (Communication ID) ─→ Analytics (B5)
Campañas (B3) ─→ Outgoing Queue (ColaBD) ─→ ccp.enviar_comunicacion
Workflows (B2) / Notification Center (B6) / IA (B9) ─→ ccp.enviar_comunicacion
Templates (B1) ─→ render de asunto/cuerpo   ·   Contacts CRM (B7) ─→ jerarquías/relaciones
```

## 5. Validaciones realizadas

- **Suite completa: 36 passed** (`smoke` + `test_correo_oauth` + `test_destinatarios` (7) + `test_ccp`
  (7) + `test_ccp_fase2` (9: B1/B3/B4/B5+B6+B10/B8/B2/B7/B9 + **API-First sin PyQt**)).
- **Sin regresiones**: envío/OAuth/Gmail/SMTP/IMAP intactos; `enviar_documento` sin cambios.
- **Multiempresa (0 cruces)** verificado en plantillas, campañas, timeline, CRM, gobierno.
- **B8 degradable**: sin credenciales, los 7 canales son `no_operativo`; único operativo = email.
- **B10**: lista negra y consentimiento revocado BLOQUEAN el envío (estado fallido, com_id registrado).
- **API-First**: test que verifica que NINGÚN servicio `ccp/*` importa PyQt.
- **Migraciones 0125–0129 reversibles** (revertir/reaplicar comprobado, incl. `conversation_id`).

## 6. Riesgos detectados y mitigación

- **Canales externos/IA sin credenciales**: degradables (`no_operativo`/determinista); sin dependencias
  duras nuevas (imports perezosos de `requests`). *Riesgo bajo.*
- **Esperas de workflow (B2)**: hoy simuladas/diferidas; el despacho temporal real se conectará al
  scheduler de jobs. *Riesgo bajo, documentado.*
- **Volumen de campañas**: la Outgoing Queue procesa síncrona por lotes; para gran escala, mover el
  `procesar()` a un job del scheduler. *Riesgo bajo.*

## 7. Compatibilidad mantenida

100% aditivo. El motor de envío, OAuth, Gmail, SMTP, IMAP, plantillas antiguas, Directorio, Agenda,
historial y auditoría siguen exactamente igual. El render de plantillas del servicio degrada al sistema
anterior si no hay plantilla nueva. Firmas públicas por palabra clave (ampliables sin romper).

## 8. Plan de rollback

- **Migraciones**: `revertir` de 0129→0125 (elimina tablas Fase II y `conversation_id`). Comprobado.
- **Servicios**: eliminar los módulos `ccp/*` nuevos y sus exports del `__init__` no afecta a la CCP
  Fase I ni al correo.
- **Pipeline de gobierno**: si se retira, `enviar_comunicacion` deja de evaluar políticas (envío como
  Fase I). GUI: quitar el botón "CCP".

## 9. Preparación para futuras fases

- **SaaS/licenciamiento**: todo por `id_empresa`; los servicios son la base de una API pública.
- **API REST/móvil/portal/IA**: al ser API-First (sin PyQt, objetos serializables), exponer una capa
  REST es directo (envolver las funciones del paquete `ccp`).
- **Microservicios**: cada bloque es un servicio desacoplado; extraíble a proceso propio.
- **Canales reales**: activar un canal = configurar credenciales (env/secret_manager); el adaptador ya
  existe. IA real = configurar backend; el asistente ya consume la IA existente.

## 10. Recomendaciones técnicas para la siguiente evolución

1. **Scheduler** para B2 (esperas) y B3 (procesar cola/campañas programadas) como jobs opt-in.
2. **API REST** fina sobre `src/services/ccp` (FastAPI/Flask) reutilizando las firmas actuales.
3. **Webhooks de estado** (entregado/leído) por canal para enriquecer Analytics/Timeline.
4. **Editor visual de plantillas** (GUI) y **panel de gobierno/consentimientos** (GUI), consumiendo
   `templates`/`gobierno`.
5. **Enriquecer Conversation** con entrantes de todos los canales cuando B8 esté operativo.

---

**Resultado:** la CCP queda consolidada como el **núcleo único, transversal y permanente** de todas las
comunicaciones de Smart Manager AI (correo, mensajería, notificaciones, campañas, automatizaciones y
comunicaciones documentales), con arquitectura limpia, escalable, multiempresa, auditable (Communication
ID), API-First y preparada para SaaS y para cualquier módulo presente o futuro.
