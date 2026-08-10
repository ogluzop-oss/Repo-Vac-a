# ARQUITECTURA — S3 MULTI-TENANT (Fase 10)

Aislamiento estricto de documentos por tenant sobre S3, aplicado **en software** (defensa en profundidad) y
reforzado por **IAM** (defensa perimetral).

## Modelo de claves

```
tenant/{id_empresa}/{tipo}/{nombre}
  → en S3:  s3://<bucket>/<S3_PREFIX?>/tenant/{id_empresa}/{tipo}/{nombre}
```

## Doble control (nunca confiar sólo en el path)

1. **Guard de software** (`storage/base.StorageProvider`): TODA operación valida que la clave pertenece a
   `tenant/{id_empresa}/`. Rechaza: `id_empresa` vacío, `..`, `/` inicial, `\`, o clave de otro tenant
   (`TenantIsolationError`). Verificado por tests (A≠B, path traversal, manipulación de id).
2. **URL prefirmada con autorización**: `url_firmada(id_empresa, clave, usuario=, autorizado=)` sólo emite si
   el tenant coincide **y** el llamador confirma la autorización RBAC del usuario. Nunca se firma "a ciegas".
3. **IAM** (perímetro): política de la task role con condición de prefijo por tenant cuando aplique; bucket
   **privado** (Block Public Access ON); acceso sólo vía la API (URLs prefirmadas) o CloudFront OAC.

## Seguridad del bucket

- Block Public Access ON; sin ACLs públicas.
- Cifrado en reposo: `S3_SSE=AES256` (SSE-S3) o `aws:kms` + `S3_KMS_KEY_ID` (SSE-KMS).
- Versioning ON + lifecycle (transición a IA/Glacier para históricos; expiración de temporales).
- Documentos sensibles (RRHH, nóminas, contratos, facturas, legales, auditorías) SIEMPRE privados.

## Pruebas de aislamiento (implementadas)

- Tenant A guarda → A lee ✔ · B lee/borra/firma/metadatos → `TenantIsolationError` ✔.
- Manipular path (`../`, prefijo de otro tenant, ruta absoluta) → falla ✔.
- URL firmada sin autorización → falla ✔.
- `id_empresa` ausente → falla ✔.

Estas garantías son idénticas en el backend local y en S3 (viven en la clase base) → el aislamiento se
prueba HOY sin AWS.
