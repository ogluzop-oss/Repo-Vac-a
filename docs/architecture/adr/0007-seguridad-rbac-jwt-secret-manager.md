# ADR-0007: Seguridad — RBAC/ACL + JWT/API Keys + Secret Manager

- **Estado**: Aceptado
- **Fecha**: 2026-07-18

## Contexto

La plataforma requiere autenticación, autorización granular por empresa/rol, integraciones
máquina-a-máquina y gestión de secretos sin exponerlos.

## Decisión

- **Autenticación**: JWT (`seguridad.tokens`) para usuarios/sesiones; **API Keys** (`X-API-Key` +
  `X-Empresa-Id`) para integraciones. MFA TOTP disponible.
- **Autorización**: RBAC/ACL (`services/autorizacion` + `services/seguridad`), catálogo de permisos
  (`seguridad/catalogo.py`), decoradores y `requiere_auth(permiso)` en la API; roles de sistema
  SUPERADMIN/ADMINISTRADOR/GERENTE/OPERARIO. Rate limit por IP+ruta.
- **Secretos**: **nunca en código ni en claro**. Se cifran con el **Secret Manager Enterprise**
  (`seguridad.secret_manager`); las conexiones guardan credenciales cifradas o `secret_ref`.

## Consecuencias

- (+) Seguridad coherente en UI, API y conectores; auditable.
- (+) Credenciales protegidas; degradable si el vault no está.
- (−) Cada superficie nueva debe pasar por `requiere_auth`/RBAC y por el Secret Manager.
