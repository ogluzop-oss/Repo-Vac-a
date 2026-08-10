# RUNBOOK DE PRODUCCIÓN — Smart Manager AI (SaaS cloud)

Guía operativa para desplegar y operar Smart Manager AI como SaaS. Reutiliza EXCLUSIVAMENTE la
infraestructura existente (sin arquitecturas paralelas). Lo que depende de recursos externos (cuenta cloud,
DNS, TLS, regiones) se marca **[EXTERNO]** y no se simula.

---

## 1. Arquitectura (jerarquía de aislamiento)

```
EMPRESA (tenant, id_empresa)
  ├─ TIENDA (id_tienda) ─ ALMACÉN (id_almacen)
  ├─ USUARIOS (RBAC + MFA)
  └─ DATOS  →  aislados por id_empresa (directa) / vía padre FK / vía usuario / global-plataforma
REGIÓN [EXTERNO]  →  saas_regiones (resolución Region→Cluster→Node→Tenant preparada, no desplegada)
```
Aislamiento verificado automáticamente: `tests/unit/test_cloud_infra.py` (418 tablas aisladas; allowlist
revisada de excepciones legítimas — hijas por FK / plataforma global). Guard estático:
`services/seguridad/tenant_guard`.

## 2. Configuración por entorno (DEV / STAGING / PROD)

- Plantilla: **`.env.example`** (sin secretos reales). Variables: `DB_*`, `API_CORS_ORIGINS`,
  `SMART_MANAGER_JWT_SECRET`, `SM_OBJECT_STORAGE_URL`, `GOOGLE_OAUTH_*`.
- **Nunca** usar credenciales de producción en DEV ni datos reales en tests (la suite exige BD `*_test`).
- Secretos: **Secret Manager** (`services/seguridad/secret_manager`: cifrar/descifrar/rotar/`disponible_vault`).
  Nunca en logs, Git ni backups sin cifrar.

## 3. Despliegue reproducible

1. **Provisionar**: `docker compose -f docker-compose.prod.yml up -d` (db `mariadb:11` + backend).
2. **Migraciones**: `python -c "from src.db import migrador; migrador.aplicar_pendientes()"` (idempotente,
   versionadas en `src/database/migraciones`).
3. **Health**: `GET /health/ready` debe devolver `200 {"status":"ok"}` antes de recibir tráfico.
4. **Observabilidad**: `services/observabilidad` (health/metricas/alertas/tracing/dashboards) activa.
5. **Rollback**: desplegar la imagen/tag anterior + `migrador` no destructivo; restaurar backup si procede.

## 4. CI/CD

`.github/workflows/`: `ci.yml`, `tests.yml`, `multiplataforma.yml`. Secuencia: commit → tests → build.
**No** promover a producción con tests/migraciones/health en rojo. Despliegue a PROD: **[EXTERNO]** (requiere
runner + credenciales cloud).

## 5. Health checks (orquestador)

- `GET /health/live` → 200 (liveness: el proceso responde).
- `GET /health/ready` → 200 si la BD es accesible, **503** si no (readiness para el balanceador).
- `GET /health/version` → 200 (versión de API; sin datos sensibles).
- Estado detallado (autenticado, por tenant): `/system/status`, `/system/status/tenant`, `/system/selftest`.

## 6. Backups · Restore · RPO/RTO

- Motor: **`services/dr/backup_operacional.py`** (`planificar`, `verificar`, `restaurar_tenant`,
  `restaurar_parcial`, `exportar_tenant`, `estado`) + `saas/backup_tenant.exportar_empresa`.
- **RPO objetivo**: ≤ 24 h (backup programado diario; ajustable con `planificar(intervalo_horas=...)`).
- **RTO objetivo**: restauración de un tenant desde export (`restaurar_tenant`) — medir en el simulacro.
- **Restore test (obligatorio)**: `backup_operacional.simulacro("restore")`. **Un backup no restaurado NO
  está validado.** La validación en infra de producción real queda **[PENDIENTE DE VALIDACIÓN EN PRODUCCIÓN]**.
- Cifrado + retención: gestionar en el almacenamiento destino ([EXTERNO] object storage `SM_OBJECT_STORAGE_URL`).

## 7. Recuperación ante desastres (DR)

```
REGIÓN PRIMARIA --fallo--> promover REGIÓN SECUNDARIA --> restaurar último backup --> readiness --> tráfico
```
Modelado en `platform/cloud/failover` (roles Primary→Secondary) y `services/dr`. **Failover real =
[EXTERNO]** (nodos/regiones desplegados). No se simula HA sin infraestructura real.

## 8. Escalabilidad

- **Stateless** (escalables horizontalmente): API REST (`src/api`), workers/jobs (idempotentes), generación
  PDF, cálculo. Preparados para múltiples réplicas tras un balanceador.
- **Stateful**: MariaDB (réplica/replicación = [EXTERNO]), almacenamiento de documentos, sesiones (JWT
  stateless ayuda). Cuellos a vigilar: pool de conexiones BD, scheduler, IA/Prophet.

## 9. Seguridad de producción

TLS/HTTPS **[EXTERNO]** (terminación en el balanceador/proveedor); headers/CORS (`API_CORS_ORIGINS`);
rate-limit (`seguridad.rate_limit`); **RBAC + MFA (TOTP/WebAuthn/step-up) + auth_time/amr** intactos;
API keys M2M separadas del MFA humano. No duplicar autenticación.

## 10. Dominios y TLS

Reutiliza **Canal Web** (`web_config`/`gestion_dominios`: propio/subdominio/comprado) + Secret Manager.
Registro DNS y emisión de certificados = **[EXTERNO]** (proveedor). Adaptador + configuración listos; sin
proveedor NO se simula (el diseño ya deja el canal en generación degradable).

## 11. Almacenamiento / CDN

Documentos empresariales → **privados** (`documentos/`, object storage privado). Recursos públicos (logos,
assets) → servibles por **CDN [EXTERNO]**. Separación private/public en la política de storage.

## 12. Event Bus / tiempo real

`services/eventbus` (in-process, real) + señales Qt + GraphQL subscriptions. **IN-APP real** hoy;
**NETWORK real-time (WebSocket/SSE push a clientes remotos) = preparado, sin transporte de red** — no se
simula.

## 13. Licenciamiento SaaS

`services/saas` (`licensing`/`enforcement`/`planes`/`dunning`/`suscripciones`/`branding`): el enforcement
está cableado (`menu_principal`); un tenant suspendido queda bloqueado por las reglas existentes.

---

**Regla de oro**: ningún componente se declara "operativo" si depende de credenciales/infra externa no
disponible. Ver `CERTIFICACION_CLOUD_INFRA.md` para la matriz de estado.
