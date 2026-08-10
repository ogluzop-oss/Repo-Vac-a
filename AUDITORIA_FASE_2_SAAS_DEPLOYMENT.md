# AUDITORÍA FASE 2 — PREPARACIÓN DE DESPLIEGUE SaaS REAL

Auditoría en modo lectura de la infraestructura existente (Fase 0). Confirma qué reutilizar (N7) y qué
requiere infraestructura externa. No se modificó nada durante la auditoría.

## SaaS / multi-tenant
- `services/saas/aislamiento.py` (`auditoria`/`tablas_sin_tenant`/`verificar`/`clasificar`): **418 tablas
  aisladas por tenant** (directa/vía-padre/vía-usuario), 14 excepciones REVISADAS (hijas por FK o
  plataforma global). `seguridad/tenant_guard` (análisis estático de SQL). `saas_global` (regiones/planes).
- **Sin fugas cross-tenant nuevas** (verificado por `test_cloud_infra.test_aislamiento_tenant_sin_fugas_nuevas`).

## Seguridad
- Secret Manager (`seguridad/secret_manager`: cifrar/descifrar/rotar/`disponible_vault`, backend
  fernet/vault). JWT (`seguridad/tokens`: `emitir_access`, `mfa_reciente`, `auth_time`/`amr`). MFA
  TOTP/WebAuthn/step-up (arquitectura congelada). API keys M2M separadas del MFA humano.

## Persistencia
- MariaDB (`db/conexion`: pool, `obtener_conexion`), migraciones versionadas (`db/migrador.aplicar_pendientes`,
  idempotentes), backups/restore (`dr/backup_operacional`, `saas/backup_tenant`).

## Infraestructura como código
- `Dockerfile`, `docker-compose.yml`, `docker-compose.prod.yml` (db mariadb:11 + backend), CI
  `.github/workflows/{ci,tests,multiplataforma}.yml`, `.env.example`. **No hay Terraform/Ansible/K8s** →
  IaC de red/VPC/LB/regiones es [EXTERNO] (depende del proveedor).

## Observabilidad
- `services/observabilidad/{health,estado,metricas,alertas_tecnicas,tracing,correlation,dashboards}`.
  Health live/ready/health; estado global/por-módulo/por-tenant/self-test.

## SaaS licensing
- `services/saas/{licensing,enforcement,planes,dunning,suscripciones,metricas,branding}`. Enforcement
  cableado en `menu_principal`; tenant suspendido bloqueado por reglas existentes.

## Veredicto
Infraestructura de **software SaaS madura y real**. Lo pendiente es **provisionado externo** (proveedor
cloud, regiones, DB productiva, object storage, CDN, DNS, TLS, CD runner, credenciales OAuth). Detalle y
pasos del propietario en `BLOQUEOS_EXTERNOS_FASE_2.md`. Cambios de esta fase: solo aditivos (config de
entornos + tests locales + documentación). N7 intacto.
