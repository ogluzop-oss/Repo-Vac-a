# INFORME — Corporate Communication Platform (CCP)

**Proyecto:** Smart Manager AI · **Bloque:** Evolución del Correo → plataforma corporativa de
comunicaciones · **Estado:** implementado y validado · **Fecha:** 2026-07-12

---

## 1. Objetivo cumplido

El módulo de Correo evoluciona (sin reescribirse ni cambiar su envío) hasta convertirse en el **primer
canal funcional** de una **Corporate Communication Platform (CCP)**: un núcleo corporativo único,
desacoplado y multicanal desde el que cualquier módulo solicita comunicaciones. En esta fase **solo el
canal Email es operativo**; el resto (WhatsApp, SMS, Push, Teams, Slack, Firma) quedan **preparados
arquitectónicamente sin envío real**.

---

## 2. Arquitectura implementada

Capa nueva **agnóstica de framework** en `src/services/ccp/`, que reutiliza toda la infraestructura
existente. La CCP **nunca consulta tablas directamente**: pasa siempre por el **Corporate Identity
Resolver**.

```
Corporate Communication Service  (servicio.py)  ── punto ÚNICO de envío
   ├── Corporate Identity Resolver (identidad.py)  ── única vía de localización de entidades
   │       ├── Recipient Resolution Service   (src.services.destinatarios — intacto)
   │       ├── Smart Organization Resolver    (organizacion.py)
   │       └── IOC                            (src.services.identidad)
   ├── Intelligent Recipient Engine (motor.py)     ── reglas por tipo de documento
   ├── Channel Policy (politica_canal.py)          ── elige canal (hoy → email)
   ├── Canales (canales/)                          ── EmailChannel operativo + 6 preparados
   ├── Outgoing Queue (cola.py)                    ── preparada (sin implementar)
   ├── Plantillas (plantillas.py)                  ── envuelve plantillas_correo + ganchos
   ├── Automatizaciones (automatizaciones.py)      ── puntos de extensión no-op
   └── Telemetría (telemetria.py)                  ── métricas Prometheus + OTel + eventos
```

**Communication ID:** cada comunicación recibe `COM-AAAA-NNNNNNNN`, independiente del canal, que
unifica auditoría/historial/telemetría (migración `0124_ccp_comunicaciones`, tabla `ccp_comunicaciones`
con estado por canal: preparada/enviado/entregado/fallido/no_operativo).

---

## 3. Componentes y responsabilidades

| Componente | Función |
|---|---|
| **Corporate Communication Service** (`enviar_comunicacion`) | Punto único. Genera com_id → resuelve destinatario/plantilla (vía Identity Resolver) → Channel Policy elige canal → DELEGA el envío al canal → historial + auditoría + eventos + telemetría. Nunca envía directamente. |
| **Corporate Identity Resolver** | Resuelve CUALQUIER entidad (empresa, tienda, almacén, centro, departamento, usuario, empleado, cliente, proveedor). Coordina Recipient Resolution + Organization Resolver + IOC. La CCP no toca tablas. |
| **Recipient Resolution Service** | El servicio de destinatarios del bloque anterior, ahora INTERNO a la CCP. Comportamiento intacto (multiempresa, histórico, favoritos, fuzzy, contexto). |
| **Smart Organization Resolver** | Organización → departamentos/contactos con correo (p. ej. Mercadona → compras@ / facturas@). Jerarquía Empresa→Delegación→Centro→Departamento→Persona, extensible. |
| **Intelligent Recipient Engine** | Reglas por tipo documental (destinatario/departamento/correo/canal/idioma/plantilla/prioridad). Semillas: factura→cliente/facturación, pedido→proveedor/compras, nómina→empleado/RRHH, contrato→RRHH… Registro extensible con una línea. |
| **Channel Policy** | Selección de canal. Hoy → email; extensible por `canal_preferido` del destinatario sin tocar el resto. |
| **Canales** | `EmailChannel` OPERATIVO (envuelve `correo.enviar_documento`, respeta el buzón elegido); WhatsApp/SMS/Push/Teams/Slack/Firma PREPARADOS (`disponible()`=False, sin envío real). |
| **Outgoing Queue / Plantillas / Automatizaciones / Telemetría** | Preparados: cola (hueco para masivos/campañas), plantillas (envuelve `plantillas_correo` + ganchos firma/logo/pie), automatizaciones (no-op), telemetría (Prometheus + OTel + Event Bus). |

**Perfil de destinatario (Parte F):** `Destinatario` ampliado con campos OPCIONALES preparados
(departamento, cargo, idioma, canal_preferido, correo_preferido, rgpd, ultimo_contacto,
num_comunicaciones, fecha_ultimo_envio, foto, tipo_entidad). Aditivo y retrocompatible.

---

## 4. Módulos integrados

- **Correo = primer consumidor de la CCP:** el `EnviarDocumentoDialog` y
  `enviar_documento_por_correo(...)` envían a través de `ccp.enviar_comunicacion(canal="email", …)`,
  que internamente usa el MISMO `correo.enviar_documento` y **respeta el buzón elegido** por el usuario
  (`id_correo`). Salida idéntica. Respaldo directo si la CCP no estuviera disponible.
- **Directorio Corporativo** (`src/gui/directorio_corporativo.py`): evolución de la Agenda con
  navegación **Internos/Externos** (datos vivos, sin duplicar). La Agenda se conserva y abre el
  Directorio.

---

## 5. API pública estable (Parte M)

`enviar_comunicacion`, `resolver_identidad`, `resolver_destinatarios`, `resolver_documento`,
`resolver_documento_inteligente`, `resolver_organizacion`, `buscar_destinatarios`, `registrar_envio`,
`registrar_favorito`, `registrar_evento`, `registrar_regla_documento`, `historial_comunicaciones`.
Firmas por palabra clave con valores por defecto → ampliables sin romper compatibilidad.

---

## 6. Reutilización de la infraestructura existente (sin duplicar)

Envío `correo.enviar_documento` (intacto) · Destinatarios `src.services.destinatarios` (interno) ·
Plantillas `plantillas_correo` · Eventos `services.eventos` · Notificaciones `services.notificaciones` ·
Telemetría `observabilidad.metricas`/`tracing` · IOC `src.services.identidad` · Buzones `db.correo`.

---

## 7. Validaciones realizadas (Parte N)

- **Sin regresiones:** envío de correo, OAuth, Gmail, SMTP, IMAP intactos (firma de `enviar_documento`
  sin cambios; suite OAuth verde).
- **Envío por CCP:** Email operativo escribe el .eml (buzón simulado), asigna Communication ID y
  registra historial/estado. Buzón concreto respetado; por contexto elige buzón afín.
- **Canales preparados:** solo `email` operativo; WhatsApp/SMS/Push/Teams/Slack/Firma devuelven
  `no_operativo` (sin envío real).
- **Resolución organizativa:** organización → departamentos/correos (info@ + facturas@).
- **Motor documental:** factura → cliente + plantilla facturas + departamento facturación.
- **Multiempresa (0 cruces):** una empresa jamás resuelve destinatarios/organizaciones de otra.
- **API pública estable** verificada.
- **Suite:** `smoke` + `test_correo_oauth` + `test_destinatarios` (7) + `test_ccp` (7) → **27 passed**.
- **Migración 0124 reversible** (revertir elimina la tabla, aplicar la recrea).

Comando: `QT_QPA_PLATFORM=offscreen DB_NAME=smart_manager_test python -m pytest -o addopts="" -q -p
no:cacheprovider tests/smoke_test.py tests/integration/test_correo_oauth.py tests/unit/test_destinatarios.py tests/unit/test_ccp.py`

---

## 8. Riesgos y mitigación

- **Cambio del punto de envío del diálogo:** mitigado con respaldo directo (si la CCP falla al
  importar, el diálogo llama a `enviar_documento` como antes) y con salida idéntica. *Riesgo bajo.*
- **Selección de buzón:** la CCP respeta el `id_correo` elegido por el usuario; sin él, elige por
  contexto/general. *Riesgo bajo.*
- **Difusa en identificadores cortos:** NIFs muy parecidos pueden emparejar por similitud (siempre
  dentro de la misma empresa; nunca cruza empresas). *Riesgo bajo, no afecta al aislamiento.*

---

## 9. Rollback

- **Migración:** `0124_ccp_comunicaciones` reversible.
- **Integración:** 100% aditiva. El canal Email envuelve el envío existente; revertir el enrutado del
  diálogo a la llamada directa (que ya está como respaldo) deja el Correo idéntico al estado previo.
  El motor de envío no se modificó.
- **Plataforma:** eliminar `src/services/ccp` y los consumidores GUI nuevos no afecta a nada previo.

---

## 10. Evolución futura

- **Canales reales:** sustituir un stub preparado por su implementación operativa (WhatsApp/SMS/…) sin
  tocar el resto; la Channel Policy y la Outgoing Queue ya están listas.
- **Outgoing Queue:** conectar la cola para envíos masivos/campañas/asíncronos.
- **Políticas de canal y preferencias:** el perfil ampliado (canal_preferido, idioma, rgpd) y la
  Channel Policy permiten enrutar por preferencia del contacto.
- **Automatizaciones:** recordatorios/programados/bots/workflow vía el registro preparado.
- **Observabilidad:** métricas Prometheus + trazas OTel ya cableadas; integración con dashboards.

---

## 11. Resultado

El Correo es ahora la **primera implementación funcional de la Corporate Communication Platform**.
Cualquier comunicación corporativa del ERP puede reutilizar la misma infraestructura —desacoplada,
escalable, multiempresa, auditable (Communication ID) y preparada para nuevos canales— sin romper la
compatibilidad con el sistema actual.
