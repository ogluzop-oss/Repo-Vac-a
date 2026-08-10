# CHECKLIST — SEGURIDAD DE PRODUCCIÓN

## Transporte / red
- 🟣 TLS/HTTPS (terminación en el balanceador/proveedor). [EXTERNO]
- 🟢 CORS restringido (`API_CORS_ORIGINS` = dominios reales, sin `*`).
- 🟢 Rate limiting (`seguridad.rate_limit`) activo en endpoints de auth/API.
- 🟢 Cabeceras de seguridad (security headers) aplicadas por la capa API.

## Identidad / autenticación (arquitectura MFA congelada — NO duplicar)
- 🟢 Contraseñas Argon2id + lockout.
- 🟢 JWT con `auth_time`/`amr`; `mfa_reciente` derivado del token real.
- 🟢 MFA TOTP + recovery codes + WebAuthn/passkeys + dispositivos de confianza.
- 🟢 Step-up en acciones críticas (`pedir_step_up`/`requiere_step_up`).
- 🟢 API keys / M2M **separadas** del MFA humano.
- 🟢 RBAC (`services.autorizacion`) transversal.

## Secretos
- 🟢 Secret Manager (`secret_manager`, backend `vault` recomendado en prod); rotación/expiración/revocación.
- 🟢 **Ningún secreto en Git/logs/backups sin cifrar** (`.env*.example` solo placeholders; verificado por
  `test_saas_deployment.test_env_examples_sin_secretos`).
- 🟢 Secretos separados por entorno (DEV/STAGING/PROD); nunca reutilizar prod en dev/local.

## Datos / tenant
- 🟢 Aislamiento multi-tenant verificado (`test_cloud_infra`); `tenant_guard` para SQL.
- 🟢 RGPD (`seguridad/rgpd`), auditoría (`log_auditoria`), anomalías (`seguridad/anomalias`).

## Observabilidad segura
- 🟢 Nunca registrar contraseñas/TOTP/recovery codes/tokens/claves (saneado en eventos MFA).

## API pública
- 🟢 OAuth2 client-credentials + scopes + expiración/revocación; sin exponer endpoints internos.
