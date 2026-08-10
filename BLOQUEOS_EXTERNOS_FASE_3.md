# BLOQUEOS EXTERNOS — FASE 3 (despliegue a producción)

El despliegue a producción está **bloqueado** porque en este entorno NO existe infraestructura real (sin
cuenta cloud, sin Docker en ejecución, BD local de desarrollo, sin storage/DNS/TLS/CD/2ª-región/credenciales
OAuth). **No se simula nada.** Este documento es el hand-off para el propietario.

> **Regla de seguridad (Fase 26):** Claude Code NUNCA escribe valores de secretos en el repo. Abajo se
> indican **nombres de variable + secret manager + entorno + proveedor**; los VALORES los provee el
> propietario en el secret store (nunca en Git, código, Dockerfile ni `.env` versionado).

Formato por bloqueo: (1) recurso · (2) motivo · (3) proveedor recomendado · (4) pasos del propietario ·
(5) configuración a entregar (nombres de variable) · (6) qué podrá hacer Claude Code después · (7) estado.

---

## B1 · Cuenta y proyecto cloud
1. Cuenta cloud + proyecto/subscription. 2. Ejecutar toda la plataforma en producción. 3. AWS / GCP / Azure
/ Hetzner / DigitalOcean. 4. Crear cuenta, presupuesto + alertas de coste, IAM con mínimos privilegios,
región primaria. 5. `CLOUD_PROVIDER`, `PRIMARY_REGION` (+ credenciales de despliegue en el secret store del
CI). 6. Parametrizar IaC/manifiestos y orquestar el despliegue. 7. 🟣 BLOQUEADO.

## B2 · Runtime de contenedores + registro de imágenes
1. Host con Docker/orquestador + registro. 2. Construir y ejecutar la imagen versionada. 3. Docker Engine /
Kubernetes gestionado + GHCR/ECR/GCR. 4. Habilitar Docker daemon (aquí NO corre), crear registro, permisos
de push/pull. 5. `IMAGE_REGISTRY`, `RELEASE_TAG`/`COMMIT_SHA`. 6. Build reproducible (no `latest`), push y
deploy. 7. 🟣 BLOQUEADO (Docker no en ejecución).

## B3 · MariaDB productiva + réplica
1. MariaDB gestionada con backups + réplica (2ª región). 2. Persistencia real HA (hoy solo `127.0.0.1`
dev). 3. RDS/Cloud SQL/Azure DB for MariaDB. 4. Provisionar instancia + réplica, backups automáticos,
usuario de app con mínimos privilegios, cifrado en reposo. 5. `DB_HOST`, `DB_USER`, `DB_PASSWORD`,
`DB_NAME`, `DB_PORT` (secret store); endpoint de la réplica. 6. Migrar (`migrador.aplicar_pendientes`),
readiness, smoke tests. 7. 🟣 BLOQUEADO.

## B4 · Object storage privado + CDN
1. Bucket privado (documentos/backups) + CDN (assets públicos). 2. Documentos RRHH/nóminas/contratos deben
ser privados; assets por CDN. 3. S3/GCS/Azure Blob + CloudFront/Cloud CDN. 4. Crear bucket **privado**,
política de acceso, URLs firmadas, CDN solo para público. 5. `SM_OBJECT_STORAGE_URL`, `CDN_DOMAIN` +
credenciales de firma (secret store). 6. Conectar el adaptador de storage; servir documentos con URL
firmada. 7. 🟣 BLOQUEADO.

## B5 · DNS + dominios
1. Dominio + DNS gestionado. 2. `app./api./admin.` públicos. 3. Registrador + Route53/Cloud DNS/Cloudflare.
4. Registrar dominio, crear A/CNAME hacia el balanceador. 5. dominios finales + acceso a la zona (o
delegación al adaptador de Canal Web). 6. Configurar rutas/hosts y validar resolución. 7. 🟣 BLOQUEADO.

## B6 · Certificados TLS
1. Certificados por dominio/wildcard + renovación. 2. HTTPS público (no autofirmado). 3. ACME/Let's Encrypt
o el gestor del proveedor/balanceador. 4. Emitir, activar renovación automática, HSTS y redirección
HTTP→HTTPS. 5. confirmación de emisión (o delegar al balanceador). 6. Validar HTTPS/expiración/redirección.
7. 🟣 BLOQUEADO.

## B7 · Runner de CD + staging/producción
1. Runner de despliegue con gates/approvals + entornos staging y prod. 2. Promover commit→staging→prod con
aprobación. 3. GitHub Actions self-hosted / GitLab CI / runner del proveedor. 4. Registrar runner con
credenciales, definir pipeline (test→build→security→staging→smoke→approval→prod), rollback N→N-1. 5.
secretos de despliegue en el store del CI. 6. Ejecutar despliegues reproducibles con rollback. 7. 🟣
BLOQUEADO.

## B8 · Secret Manager / KMS de producción
1. KMS/Vault gestionado. 2. Custodia/rotación de secretos en prod (hoy backend `fernet` local). 3. AWS
KMS+Secrets Manager / GCP Secret Manager / HashiCorp Vault / Azure Key Vault. 4. Provisionar, cargar
secretos por entorno, políticas de acceso y rotación. 5. `SM_SECRET_BACKEND=vault` + endpoint/credenciales
del vault. 6. Resolver todos los secretos desde el vault en runtime. 7. 🟣 BLOQUEADO.

## B9 · Credenciales OAuth de terceros (conectores)
1. Apps OAuth reales por proveedor. 2. Conectores CONNECTED (hoy AUTH_REQUIRED). 3. Google/Microsoft/Stripe
/PayPal/marketplaces. 4. Crear app OAuth en cada proveedor, configurar redirect URIs, obtener client_id/
secret. 5. `GOOGLE_OAUTH_CLIENT_ID/SECRET`, `STRIPE_*`, `PAYPAL_*`, `MS365_*` (secret store; NUNCA en Git).
6. Autenticar y probar lectura/escritura reales por conector, con auditoría. 7. 🟣 BLOQUEADO.

## B10 · Validación real RPO/RTO + failover
1. Infra de prod + 2ª región para cronometrar. 2. Medir pérdida de datos (RPO) y tiempo de recuperación
(RTO) reales; probar failover. 3. (depende de B1–B3). 4. Ejecutar `backup_operacional.simulacro` sobre BD/
región reales, cronometrar restore y failover. 5. hora de fallo/detección/recuperación + datos perdidos.
6. Actualizar `CERTIFICACION_CLOUD_INFRA.md`/`CERTIFICACION_PRODUCCION_FINAL.md` (🟡→🟢). 7. 🟣 BLOQUEADO.

---

**Estado global:** el despliegue a producción NO puede ejecutarse hasta B1–B10. El software está listo; solo
faltan estos recursos externos. Al proporcionarlos, el despliegue se ejecuta sin rediseñar el software.
