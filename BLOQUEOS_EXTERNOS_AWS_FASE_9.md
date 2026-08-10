# BLOQUEOS EXTERNOS — AWS (Fase 9)

Recursos que **debe provisionar el propietario** antes de la implementación AWS. **Nunca se escriben valores de
secretos**: sólo nombres de variable. Estado de todos: 🟣 BLOQUEADO POR RECURSO EXTERNO (no simulado).

---

### B1 · Cuenta y organización AWS
1. **Recurso**: cuenta(s) AWS (DEV/STAGING/PROD), org, budgets.
2. **Motivo**: sin cuenta no hay ningún servicio.
3. **Servicio**: AWS Organizations / Billing.
4. **Pasos**: crear cuenta, MFA root, IAM admin inicial, budgets + alarmas de coste.
5. **Variables**: `AWS_ACCOUNT_ID`, `AWS_REGION`.
6. **Después (Claude Code)**: generar IaC base (VPC/ECS/RDS/S3).
7. **Estado**: 🟣.

### B2 · Red (VPC)
1. VPC, subnets públicas/privadas, NAT, SG, VPC endpoints (S3/Secrets/ECR/Logs).
2. Aislar RDS/ECS en privado; ALB en público.
3. Servicio: VPC.
4. Pasos: provisionar por IaC (Claude Code prepara plantillas; propietario aplica con credenciales).
5. Variables: `VPC_ID`, `SUBNET_IDS`, `SG_IDS`.
6. Después: desplegar ECS/RDS en la VPC.
7. Estado: 🟣.

### B3 · RDS MariaDB
1. Instancia RDS MariaDB 11 (Multi-AZ), parameter group utf8mb4/UTC, CA bundle.
2. Persistencia gestionada + backups.
3. Servicio: Amazon RDS.
4. Pasos: crear instancia, credenciales en Secrets Manager, activar TLS.
5. Variables: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (Secrets), `DB_SSL_CA`.
6. Después: aplicar migraciones y validar conexión TLS.
7. Estado: 🟣.

### B4 · S3 + KMS + CloudFront (documentos)
1. Bucket privado, CMK KMS, distribución CloudFront con OAC.
2. Almacenamiento de ficheros efímero en Fargate → S3.
3. Servicios: S3, KMS, CloudFront.
4. Pasos: crear bucket (Block Public Access), CMK, distribución OAC + política SSE.
5. Variables: `S3_BUCKET`, `KMS_KEY_ID`, `CDN_DOMAIN`.
6. Después: activar backend S3 en la capa `storage` + URLs firmadas.
7. Estado: 🟣.

### B5 · Secrets Manager
1. Secretos: JWT, DB, OAuth Google, clave de correo.
2. Sacar secretos del filesystem/env plano.
3. Servicio: AWS Secrets Manager (+ KMS).
4. Pasos: crear secretos + rotación; conceder acceso a roles ECS/CI.
5. Variables (sólo NOMBRES): `SMART_MANAGER_JWT_SECRET`, `DB_PASSWORD`, `GOOGLE_OAUTH_CLIENT_SECRET`, `correo_key`.
6. Después: implementar backend AWS en `secret_manager` (punto de extensión ya existe).
7. Estado: 🟣.

### B6 · ECR + ECS Fargate + ALB
1. Repo ECR, cluster ECS, servicios `api`/`worker-ia`, ALB + target group.
2. Runtime del backend.
3. Servicios: ECR, ECS Fargate, ALB.
4. Pasos: crear repo/cluster/ALB; roles de task/execution.
5. Variables: `ECR_REPO`, `ECS_CLUSTER`, `ALB_ARN`, `TASK_CPU/MEM`.
6. Después: task defs + autoscaling + pipeline de deploy.
7. Estado: 🟣.

### B7 · Route 53 + ACM + WAF
1. Dominio + zona, certificados TLS, reglas WAF.
2. Exposición pública segura (app./api./admin.).
3. Servicios: Route 53, ACM, AWS WAF.
4. Pasos: registrar dominio, crear zona, emitir cert ACM, asociar WAF a CloudFront/ALB.
5. Variables: dominios `app.`, `api.`, `admin.smartmanager.ai`.
6. Después: configurar CloudFront/ALB + cabeceras SSE.
7. Estado: 🟣.

### B8 · CI/CD (OIDC)
1. Rol de despliegue vía GitHub OIDC (sin claves estáticas).
2. Entrega continua a ECR/ECS.
3. Servicios: IAM (OIDC), ECR, ECS.
4. Pasos: crear proveedor OIDC + rol `sm-ci-deploy`; environments protegidos en GitHub.
5. Variables: `AWS_ROLE_ARN` (OIDC), `ECR_REPO`, `ECS_SERVICE`.
6. Después: extender workflows (build→push→deploy→smoke→approval→prod).
7. Estado: 🟣.

### B9 · Broker de tiempo real (sólo si multi-instancia)
1. Redis/NATS/SNS para fan-out SSE entre instancias ECS.
2. El Event Bus es in-process; N instancias no comparten eventos.
3. Servicios: ElastiCache Redis / MSK / SNS.
4. Pasos: provisionar broker en subnet privada.
5. Variables: `REALTIME_BROKER_URL`.
6. Después: implementar `realtime.set_distribucion` (punto de extensión ya previsto). **Sólo si se escala SSE.**
7. Estado: 🟣.

### B10 · DR (Multi-AZ / cross-region)
1. Multi-AZ RDS, S3 cross-region replication, retención.
2. Continuidad de negocio.
3. Servicios: RDS Multi-AZ, S3 CRR.
4. Pasos: activar Multi-AZ + CRR + política de retención; ejecutar simulacro real.
5. Variables: RPO/RTO objetivo, región secundaria.
6. Después: scripts de restore/simulacro sobre snapshots reales → evidencia para certificar DR.
7. Estado: 🟣.
