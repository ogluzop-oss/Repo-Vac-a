# ARQUITECTURA — SECRETS AWS (Fase 10)

## Interfaz única (no se duplica el sistema de secretos)

`services/seguridad/secret_manager` con backend intercambiable `SM_SECRET_BACKEND`:

| Backend | Comportamiento |
|---|---|
| `fernet` (por defecto) | cifra/descifra con `utils.cripto` (rotación soportada) |
| `vault` | punto de extensión (degrada a entorno) |
| `aws_secrets_manager` (Fase 10) | lee de AWS Secrets Manager vía boto3 perezoso; cache TTL 5 min |

`obtener_secreto(clave)` resuelve por el backend activo. Con AWS: `get_secret_value`. **Sin fallback inseguro
en producción**: si `ENVIRONMENT=production` y AWS no resuelve el secreto, devuelve `default` y avisa (no cae a
un valor de entorno inseguro). Fuera de producción, degrada a variable de entorno para no romper DEV.

## Mapeo a AWS

| Secreto | Destino |
|---|---|
| `SMART_MANAGER_JWT_SECRET` | Secrets Manager (rotación) |
| `DB_PASSWORD` | Secrets Manager |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Secrets Manager |
| `documentos/.correo_key` | Secrets Manager (sacar del filesystem) |
| Cifrado en reposo de datos/documentos | **KMS** (SSE-KMS en S3, CMK por entorno) |

## KMS readiness

- S3 con `S3_SSE=aws:kms` + `S3_KMS_KEY_ID`.
- CMK por entorno (dev/staging/prod); política de clave concede `encrypt/decrypt` a las task roles.
- Las claves NUNCA en Git ni en la imagen; se resuelven por IAM Role/Task Role en runtime.

## Honestidad

`disponible_aws()` refleja si boto3 está presente; no garantiza credenciales/secreto real. Sin AWS, el backend
`aws_secrets_manager` está 🔵 PREPARADO (degradable), nunca operativo.
