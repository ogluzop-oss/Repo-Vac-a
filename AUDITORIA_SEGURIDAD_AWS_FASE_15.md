# AUDITORÍA SEGURIDAD AWS — FASE 15

Fecha 2026-07-27. **BLOQUEADO para validación en AWS real: sin Secrets Manager/KMS/IAM provisionados.**

## Software (verificado)

🟢 `secret_manager` con backend `aws_secrets_manager` (boto3 perezoso, cache TTL), **sin fallback inseguro en
producción**. 0 secretos en Git/`.env.production.example` (sólo placeholders). RBAC/MFA/WebAuthn/tenant_guard/
auditoría intactos (N7). IaC sin wildcards IAM; matriz de mínimo privilegio documentada
(`AUDITORIA_SEGURIDAD_AWS.md`).

## Validación en AWS (Fase 15.8)

🟣 **BLOQUEADA**. No ejecutado: Secrets Manager real, KMS, rotación, IAM efectiva; verificación de ausencia de
secretos en task definitions reales; auditoría de seguridad sobre la infraestructura desplegada.

## Resume

Provisionar Secrets Manager + KMS + roles IAM (task/execution/worker/migration/CI OIDC, mínimo privilegio).
Variables (NOMBRES): `SM_SECRET_BACKEND=aws_secrets_manager`, `SMART_MANAGER_JWT_SECRET`, `DB_PASSWORD`,
`GOOGLE_OAUTH_CLIENT_SECRET`, `S3_KMS_KEY_ID`, `AWS_ROLE_ARN`. Nunca valores en Git. Estado: 🟢 software (0
vulnerabilidades críticas) / 🟣 controles de infra externos.
