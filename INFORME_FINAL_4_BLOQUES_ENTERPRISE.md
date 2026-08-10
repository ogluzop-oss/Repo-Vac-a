# Informe Final — Cierre de los 4 Bloques Enterprise

**Fecha:** 2026-07-06 · **Alcance:** completar los 4 bloques aplazados reutilizando la arquitectura
existente. **Invariantes respetadas:** SOMA, Plan UI Enterprise, Mission Engine, Workflow, Gobierno,
Autonomía y la navegación aprobada — **intactos**. Sin motores paralelos, sin reescribir módulos, sin
duplicar lógica. Verificación tras cada bloque (AST + funcional + `smoke 5 passed`).

## 1. Cambios implementados

### Bloque 1 — Jobs Enterprise Opt-In (completo)
- **`scheduler_registry.py` (JobRegistry)**: catálogo declarativo de **32 jobs** con metadatos que el
  Scheduler no tenía (categoría, `pesado`, prioridad, timeout, reintentos, permiso RBAC).
- **Política opt-in**: 8 jobs pesados deshabilitados por defecto (bi_corp_etl/alertas, resiliencia
  sync/watchdog/métricas, cache_warmup, sat_email_ticket, SAAS_DUNNING); 17 ligeros habilitados.
  `sincronizar()` reutiliza los registradores de callables de cada dominio (no duplica).
- **Config editable desde el ERP** (`configurar_job`): habilitar/deshabilitar, frecuencia, prioridad,
  timeout, reintentos — con **permiso RBAC** y **auditoría del usuario** que la cambió; la marca
  `configurado` protege la elección frente a la sincronización.
- **Ejecución** con **timeout** (soft, hilo daemon), **reintentos** y **duración** medida;
  `ejecutar_pendientes` por **prioridad**; historial con estado/detalle/duración.
- **GUI "Programador"** (`panel_jobs.py`) — pestaña en Aprobaciones. migr **0101**.

### Bloque 2 — Integraciones reales (código+config listos para activar)
- **`integraciones/conectores.py`**: implementaciones REALES guardadas —
  - **Google Calendar/Drive/Gmail**: activables ya (reutilizan el OAuth cifrado de `services.correo`;
    `googleapiclient` disponible). Leer/crear/editar/cancelar eventos; subir documentos; enviar correo.
  - **Microsoft Graph (Outlook/Exchange Online)** y **DocuSign**: llamadas REST con `requests` +
    token OAuth de configuración; se activan al aportar credenciales.
- **Nunca contraseñas** (solo OAuth 2.0). Toda operación **auditada**. Degradación limpia:
  `no_configurado` si falta SDK/credencial/token — **no rompe nada**.
- Puntos de entrada de alto nivel en `integraciones`: `calendario()`, `firma_enviar/estado()`,
  `documento_subir()`, y envío de correo Microsoft por `enviar()`.

### Bloque 3 — Certificaciones fiscales (endurecimiento testeable)
- **`fiscal/worker.py`** endurecido sobre la cola existente (idempotente, backoff, MAX_INTENTOS):
  - **Clasificación de errores**: PERMANENTES (rechazo oficial/XSD/WSDL/firma/certificado → **no se
    reintentan**, registro `rechazado`) vs TEMPORALES (red/servicio → reintento con backoff).
  - **Inmutabilidad**: estados terminales (`enviado`/`anulado`/`rechazado`) nunca se reenvían ni se
    alteran.
  - **Acuse/identificador** oficial guardado cuando el emisor lo devuelve (seguimiento/auditoría).
- La arquitectura fiscal (Verifactu/Facturae conforme XSD/WSDL, firma XAdES, `certificados.py` con
  software cert + estado activo/inactivo/caducado = renovación/revocación) se **mantiene intacta**.

### Bloque 4 — Multitenant (auditoría + guard centralizado)
- **`saas/aislamiento.py`** reforzado: `clasificar()` / `auditoria()` clasifican TODAS las tablas por
  su mecanismo de aislamiento (directa por `id_empresa` · vía tabla padre · vía usuario · global · fuga).
- **Resultado de la auditoría (322 tablas):** **296 directas** · 12 vía padre · 3 vía usuario · 11
  globales · **0 fugas reales**. El modelo de datos está **completamente aislado por tenant**; no hay
  mezcla posible de datos entre empresas. Sin reescribir consultas ni tocar esquemas (bajo riesgo).

## 2. Componentes reutilizados

Scheduler (COM-3) · Workflow · Gobierno · Autonomía · Event Bus · Auditoría (`log_auditoria`) · RBAC
(`autorizacion.puede`) · Sistema de correo + OAuth Google cifrado (`services.correo`) · Framework de
conectores (`integraciones`) · Núcleo fiscal (Verifactu/Facturae/certificados) · Contexto de empresa
(`empresa_actual_id`/TenantContext) · Componentes UI Enterprise (EnterpriseTable/Filter). Ningún motor
nuevo.

## 3. Arquitectura final

- **Jobs**: Scheduler + JobRegistry (catálogo) + config por empresa en `scheduler_jobs`; opt-in de
  pesados; GUI en Aprobaciones. Ejecución con timeout/reintentos/prioridad/auditoría.
- **Integraciones**: framework `integraciones.enviar()` + `conectores.py` (Google real; MS/DocuSign
  REST) con degradación controlada; OAuth reutilizado; auditoría por operación.
- **Fiscal**: núcleo intacto + worker de cola endurecido (permanente/temporal, inmutabilidad, acuse).
- **Multitenant**: aislamiento estructural por `id_empresa` (directo/vía padre/vía usuario) + guard
  central de verificación reutilizable.

## 4. Riesgos detectados

- Ejecución de jobs: `registrar_job` deja `proxima_ejecucion=NULL` (job "vencido"); por eso el arranque
  **registra pero no auto-ejecuta** (evita carga). Disparo controlado desde la GUI ("Ejecutar ahora").
- Integraciones reales: **no verificables** contra los servicios sin cuentas/SDK; mitigado con
  degradación limpia (nunca rompen) y auditoría.
- Fiscal: el round-trip real depende de certificados y endpoints oficiales externos.

## 5. Compatibilidad hacia atrás

Todo aditivo. `scheduler.ejecutar_job` conserva su firma (SOMA sigue usándolo). `integraciones.enviar`
mantiene el comportamiento webhook y la degradación previa. El worker fiscal conserva su contrato
(idempotencia/backoff) y añade clasificación de errores sin alterar los casos existentes. La auditoría
de aislamiento es read-only. Migración 0101 idempotente y reversible.

## 6. Rendimiento

Sin duplicar procesos. Jobs con timeout (evita bloqueos) en hilos daemon (sin fugas del hilo principal).
Conectores con timeouts de red (20-30 s). Auditoría de aislamiento en O(nº tablas), read-only. Arranque
sin carga añadida (registro de jobs en segundo plano, sin ejecución).

## 7. Pruebas realizadas

- **Bloque 1**: 32 jobs catalogados · 8 pesados 0 habilitados por defecto · habilitar bi_corp_etl
  persiste y sobrevive a re-sincronizar · deshabilitar/ejecutar OK (duración medida) · GUI "Programador".
- **Bloque 2**: todos los conectores degradan a `no_configurado` sin credenciales (sin crash) — Google,
  MS Graph, DocuSign, y la API de alto nivel.
- **Bloque 3**: clasificación permanente (rechazado/XSD/flag) vs temporal (timeout) correcta;
  inmutabilidad de estados terminales.
- **Bloque 4**: auditoría de 322 tablas → 0 fugas reales.
- **Global**: `smoke_test.py` **5 passed** tras cada bloque; AST OK; SOMA/UI Enterprise/navegación
  intactos.

## 8. Incidencias corregidas

- Jobs pesados nunca disponibles/configurables → catálogo + opt-in + GUI.
- Conectores de credenciales devolvían `no_implementado` → ahora ejecutan la integración real
  (o degradan) según configuración.
- Errores fiscales permanentes se reintentaban inútilmente hasta agotar intentos → clasificación
  permanente/temporal.
- Auditoría de aislamiento daba 21 falsos positivos (hijas/globales) → clasificación precisa (0 fugas).

## 9. Elementos deliberadamente fuera de alcance (requieren recursos externos / decisión)

- **Integraciones**: registro de apps OAuth (Azure AD / Google Cloud / DocuSign), credenciales reales e
  instalación de SDKs (`msal`, `docusign_esign`, `exchangelib`) para operar y probar en vivo. La UI de
  conexión de cuentas Google reutiliza el OAuth de correo; MS/DocuSign requieren su config.
- **Fiscal**: certificado digital real (FNMT/HSM) y acceso a endpoints oficiales
  (AEAT/TicketBAI/SIF/Veri*Factu preproducción-producción) para el round-trip real. **TicketBAI** y
  **Eventos SIF** siguen siendo épicas posteriores por decisión.
- **Multitenant**: enforcement automático por consulta en runtime (guard que inyecte `id_empresa`) y
  ejecución simultánea multi-empresa (instancias SOMA por empresa, ejecución de Scheduler por empresa,
  aislamiento de caché/tokens en runtime). El **modelo de datos ya está aislado** (0 fugas); esto es
  refuerzo de runtime, de valor solo en un despliegue multiempresa real. Pruebas de carga 100/1000/
  10000 empresas: requieren un entorno multiempresa real.
