# AUDITORÍA DE SEGURIDAD AWS FINAL (Fase 13)

Fecha 2026-07-27. Revisión de seguridad de las adaptaciones AWS (Fases 9-12). Read-only. Sin vulnerabilidades
críticas detectadas.

## Resultados por categoría

| Vector | Resultado | Evidencia |
|---|---|---|
| Secretos en Git / `.env.production.example` | ✅ 0 | grep: 0 secretos duros; sólo placeholders `<...>`/`[EXTERNO]` |
| Secretos en logs | ✅ | `secret_manager` no loguea valores; auditoría MFA/jobs sin secretos |
| Fallback inseguro de secretos en producción | ✅ evitado | `ENVIRONMENT=production` sin AWS → devuelve default + warning, no valor inseguro |
| Bypass tenant (storage) | ✅ bloqueado | clave/tenant desde BD; guard base; tests A≠B |
| Path traversal (storage) | ✅ bloqueado | `_validar` rechaza `..`,`/`,`\`, prefijo ajeno |
| IDOR documental | ✅ bloqueado | resolución por `id_documento`+tenant; cross-tenant → error |
| Presigned URL abuse | ✅ mitigado | sólo tras autorización (`autorizado=True`) + tenant correcto |
| Jobs cross-tenant | ✅ bloqueado | `id_empresa` obligatorio; worker ejecuta sólo en su tenant |
| Eventos cross-tenant (Redis) | ✅ bloqueado | filtro por `id_empresa`; sello no altera el aislamiento |
| SSRF | ✅ sin superficie nueva | no se construyen URLs desde input de usuario en las capas nuevas |
| S3 público | ✅ diseño privado | bucket privado + SSE-KMS + presigned (config); sin ACL pública |
| SQL inseguro | ✅ | queries parametrizadas (`%s`) en storage/idempotencia/documentos |
| IAM wildcards (`Action/Resource: "*"`) | ✅ ninguno | `main.tf` sin wildcards; matriz IAM de mínimo privilegio documentada |
| JWT / RBAC / MFA / WebAuthn | ✅ intactos | reutilizados, no duplicados (N7) |
| Rate limiting / TLS | ✅ | rate-limit propio; TLS por ACM/ALB (config); DB SSL-ready |

## Observaciones (no críticas)

- **RBAC en lectura documental**: `abrir_documento` aplica `puede(usuario, permiso)` sólo si `usuario` no es
  None (llamada interna/servicio omite RBAC pero el tenant SÍ se valida). Comportamiento intencionado y
  documentado; las superficies de usuario deben pasar `usuario`.
- **Reconexión Redis**: 🟡 pendiente (no es vulnerabilidad; robustez).

## Vulnerabilidades críticas

**Ninguna.** No se hallaron bypass de tenant, pérdida potencial de datos por diseño, ni exposición de secretos.

## Validaciones que requieren AWS real (🟣)

Políticas IAM efectivas, cifrado KMS en reposo, Block Public Access del bucket, WAF, TLS público — se validan
sobre AWS real (no simulado).

## Veredicto

🟢 **Sin vulnerabilidades críticas** en las capas AWS de software. Apto para certificación (validación de
controles a nivel de infraestructura AWS 🟣 externa).
