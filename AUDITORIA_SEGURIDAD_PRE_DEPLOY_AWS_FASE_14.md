# AUDITORÍA — SEGURIDAD PRE-DESPLIEGUE (Fase 14)

Fecha 2026-07-27. Read-only. Seguridad global previa al provisionado. Sin vulnerabilidades críticas.

## Autenticación / autorización (reutilizados, N7)

| Control | Estado | Nota |
|---|---|---|
| JWT | 🟢 | tokens con claims; guard `access` |
| RBAC | 🟢 | `services.autorizacion.puede`; catálogo de permisos |
| MFA (TOTP) | 🟢 | motor único `seguridad/mfa`; step-up acciones críticas |
| WebAuthn/Passkeys | 🟢 | `mfa_webauthn` (degradable) |
| CORS | 🟢 | `API_CORS_ORIGINS` configurable |
| HSTS | 🟢 | `API_HSTS` |
| Rate limiting | 🟢 | propio (login/mfa/step-up) |
| Tenant isolation | 🟢 | `tenant_guard` + 404 tablas directas |
| Auditoría | 🟢 | `log_auditoria` (sin secretos) |

## Vectores revisados

| Vector | Resultado |
|---|---|
| Bypass tenant (storage/eventos/jobs) | ✅ bloqueado (tests) |
| Escalada de privilegios | ✅ RBAC + rol efectivo=MAX(orgánico,perfil) |
| IDOR documental | ✅ resolución por id+tenant; cross-tenant → error |
| Cross-tenant (S3/Redis/SQS) | ✅ `id_empresa` obligatorio en cada capa |
| Presigned sin autorización | ✅ requiere `autorizado=True` + tenant |
| Secretos en repo/docs/logs | ✅ 0 (grep `.env.production.example`: 0 duros; secret_manager no loguea) |
| Fallback inseguro en producción | ✅ evitado (`ENVIRONMENT=production` → no cae a valor inseguro) |
| Endpoints sin autenticación | ✅ sólo health (`/live|/ready|/version`) es público por diseño |
| Rutas admin expuestas | ✅ tras RBAC/MFA; SUPERADMIN gated |
| SQL injection | ✅ queries parametrizadas en capas nuevas |
| IAM wildcards | ✅ ninguno en `main.tf` |

## Dependencias externas (🟣)

Controles a nivel de infraestructura que se validan sobre AWS real: bucket policy/Block Public Access, KMS,
WAF, TLS público (ACM), Security Groups (RDS no público), políticas IAM efectivas.

## Vulnerabilidades críticas

**Ninguna.**

## Veredicto

🟢 **Sin vulnerabilidades críticas de software**. Controles de infraestructura AWS 🟣 externos (validación
posterior). Apto para pre-despliegue.
