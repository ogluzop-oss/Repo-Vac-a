# AUDITORÍA TÉCNICA — IaC Terraform (revisión estática)

Fecha 2026-07-29. Revisión de solo lectura de `infra/aws/`. **No se ejecutó** terraform/aws/cdk/docker.
`terraform` no está instalado → no hay `validate`/`plan` reales; la revisión es **estática** (lectura + grep).

## Resultado por punto (1-20)

| # | Comprobación | Resultado |
|---|---|---|
| 1 | Sintaxis HCL | 🟢 sin comas-en-args; llaves balanceadas por fichero. `validate` real 🟣 (CLI ausente) |
| 2 | Módulos conectados | 🟢 root pasa `vpc_id`/subnets a rds/ecs vía `try(module.network[0]...)` |
| 3 | Variables de módulo ↔ llamadas | 🟢 coinciden (network/rds/s3/secrets/observability/ecs/iam_oidc) |
| 4 | Outputs coherentes | 🟢 usan `try(module.x[0]...)` → null si desactivado |
| 5 | Nombres consistentes | 🟢 prefijo `${project}-${environment}` (`local.name`) |
| 6 | Protección por `enable_*` | 🟢 cada módulo `count = var.enable_* ? 1 : 0` |
| 7 | 0 recursos con todo en false | 🟢 sin recursos/data a nivel raíz; los `data` viven dentro de módulos gated |
| 8 | Nada se crea por defecto | 🟢 los 7 `enable_*` = false; backend remoto comentado |
| 9 | Sin secretos en TF | 🟢 grep 0; RDS `manage_master_user_password`; `secrets` crea contenedores sin valores |
| 10 | RDS ↔ PyMySQL/DBUtils | 🟢 engine mariadb 11.4, param group `mariadb11.4`, utf8mb4; compatible |
| 11 | SSL MariaDB | 🟡 **no se fuerza TLS** (`require_secure_transport` ausente en el parameter group) |
| 12 | S3 ↔ StorageProvider | 🟢 SSE-KMS + bucket + prefijo `tenant/`; casa con `S3_BUCKET/S3_SSE/S3_KMS_KEY_ID` |
| 13 | Secrets Manager ↔ secret_manager | 🔴 **MISMATCH de nombres** (ver A-1) |
| 14 | ECS ↔ Flask/gunicorn/gevent | 🟡 compatible, pero **módulo ECS incompleto** (sin task def/service/listener HTTPS) |
| 15 | Dockerfile ↔ ECS | 🟡 non-root/gevent OK; **health path incorrecto** (ver A-2) |
| 16 | Logs ↔ CloudWatch | 🟡 log groups creados; **falta wiring awslogs en la task def** (ECS incompleto) |
| 17 | Workflow plan-only | 🟢 `apply` y `plan` comentados; sólo `fmt/init -backend=false/validate` |
| 18 | OIDC mínimo privilegio | 🟢 no puede provisionar infra (sólo ECR/ECS deploy). 🟡 recursos `*` a acotar |
| 19 | Estado remoto desactivado | 🟢 `backend.tf` comentado → estado local |
| 20 | Aislamiento DEV/STAGING/PROD | 🟡 nombres/CIDRs aislados; **estado NO aislado** hasta backend por-entorno (ver B-1) |

---

## A. PROBLEMAS ENCONTRADOS (bloquean el despliegue)

### A-1 · 🔴 Nombres de secretos: contrato roto entre app e IaC
- **App** (`secret_manager.obtener_secreto(clave)`) llama `get_secret_value(SecretId=clave)` con el nombre
  **desnudo** (p. ej. `SMART_MANAGER_JWT_SECRET`).
- **IaC** (`modules/secrets`) crea secretos con prefijo: `${name}/SMART_MANAGER_JWT_SECRET`
  (`smart-manager-dev/...`).
- **Efecto**: en producción la app NO encontraría el secreto → `default`/None (no hay fallback inseguro, pero
  falta el secreto). En dev caería a variable de entorno (enmascara el fallo).
- **Corrección (elegir una)**: (a) añadir soporte `SM_SECRET_PREFIX` en `secret_manager` y setear el prefijo
  por entorno; o (b) usar **una cuenta AWS por entorno** y nombrar los secretos sin prefijo; o (c) nombrar el
  secreto exactamente como la clave que pide la app. Recomendado: (a) prefijo por entorno.

### A-2 · ✅ FALSO POSITIVO (corregido 2026-07-29) — `/api/v1/live` SÍ existe
- **Corrección de esta auditoría**: la revisión inicial fue **incorrecta**. Además del blueprint
  `api/routers/system.py` (que expone `/api/v1/health/live`), el blueprint `src/backend/api.py`
  (`url_prefix="/api/v1"`, línea 190) registra `/live`, `/ready`, `/health`, `/metrics` → **`/api/v1/live`,
  `/api/v1/ready`, `/api/v1/health` son rutas REALES y devuelven 200**.
- **Conclusión**: el health-check `/api/v1/live` usado en `Dockerfile`, `docker-compose.prod.yml`,
  `deploy/k8s`, `deploy/helm` y el target group ECS es **válido y es la convención del repo**. **NO hay bug y
  NO se aplica ningún cambio.** (`/api/v1/health/live` también existe, pero cambiar a esa ruta desviaría de la
  convención sin beneficio.)

### A-3 · 🟡 Módulo ECS incompleto (no ejecuta la app aún)
- `modules/ecs` crea ECR + cluster + ALB + target group, pero **no** hay `aws_ecs_task_definition`,
  `aws_ecs_service`, ni listener **HTTPS** (requiere ACM). Tampoco inyecta secretos (`secrets` de la task) ni
  el driver `awslogs`.
- **Efecto**: preparado pero **no desplegable end-to-end** todavía. No es un bug; es alcance pendiente.
- **Corrección**: completar task def (image ECR + `secrets` valueFrom ARNs Secrets Manager + `logConfiguration`
  awslogs → log group del módulo observability + `DB_PASSWORD` desde el secret gestionado de RDS), service y
  listener HTTPS al integrar ACM/Route53.

---

## B. RIESGOS

### B-1 · 🟡 Estado Terraform NO aislado por entorno
- Con `backend.tf` comentado, el estado es **local y único**. Ejecutar `apply` con
  `dev.tfvars` y luego `staging.tfvars` en el mismo directorio **sobrescribiría el mismo `terraform.tfstate`**.
- **Mitigación**: configurar el backend S3 con **`key` por entorno** (ya previsto en el comentario:
  `smart-manager/<env>/terraform.tfstate`) o usar **workspaces** (`terraform workspace new dev|staging|prod`)
  ANTES de aplicar más de un entorno.

### B-2 · ✅ RESUELTO (2026-07-29, Fase 15.1) — proveedor OIDC colisión-safe
- El módulo `iam_oidc` ahora acepta `create_oidc_provider` (root: `ci_create_oidc_provider`, default `true`).
  Con `false`, **referencia** el proveedor existente vía `data "aws_iam_openid_connect_provider"` en vez de
  crearlo (sin `terraform import`). El ARN se resuelve por `local.oidc_provider_arn` en trust/outputs.
- Sin despliegue: el módulo sigue desactivado (`enable_ci_oidc=false`).

### B-3 · 🟡 TLS de MariaDB no forzado en RDS
- La app puede usar TLS (`DB_SSL_CA`), pero el parameter group no fija `require_secure_transport=ON` → RDS
  aceptaría conexiones no cifradas.
- **Mitigación**: añadir el parámetro (defensa en profundidad) antes de producción.

### B-4 · 🟡 Dependencias entre módulos al activar por partes
- Activar `enable_rds`/`enable_ecs` **sin** `enable_network` deja `vpc_id=null` → error en `plan/apply`.
- **Mitigación**: respetar el **orden de activación** (E). No es un riesgo por defecto (todo false), sí al
  activar.

### B-5 · 🟡 `terraform fmt -check` del workflow podría fallar
- El CI ejecuta `fmt -check -recursive`; el formato no se ha verificado con la CLI real.
- **Mitigación**: ejecutar `terraform fmt -recursive` una vez (propietario) antes de confiar en el gate.

### B-6 · 🟢/🟡 Permisos OIDC amplios por recurso
- El rol CI limita **acciones** (ECR/ECS) pero usa `resources=["*"]`. No puede crear infra, pero conviene
  acotar a los ARN reales del repo ECR y del cluster/servicio cuando existan.

---

## C. CORRECCIONES NECESARIAS (antes de desplegar)

1. **A-1** Resolver el contrato de nombres de Secrets Manager (prefijo por entorno en `secret_manager` **o**
   cuenta por entorno). **Bloqueante.**
2. **A-2** Corregir la ruta de health-check a `/api/v1/health/live` en ECS target group + Dockerfile + compose
   (o añadir alias). **Bloqueante.**
3. **B-1** Definir aislamiento de **estado** por entorno (backend `key` por env o workspaces) antes de aplicar
   más de un entorno. **Importante.**
4. **B-3** Forzar `require_secure_transport=ON` en el parameter group de RDS. **Recomendado.**
5. **A-3/16** Completar la task definition ECS (secrets valueFrom, awslogs, `DB_PASSWORD` desde el secret de
   RDS, listener HTTPS) — parte del alcance de despliegue.
6. **B-2** Manejar el proveedor OIDC existente (data/import) para evitar colisión.
7. **B-6** Acotar los `resources` del rol OIDC a ARNs concretos cuando existan.

---

## D. YA CORRECTAMENTE PREPARADO

- ✅ **0 recursos por defecto** (todos los `enable_*`=false; sin recursos/data a nivel raíz).
- ✅ **Sin secretos** en Terraform (RDS `manage_master_user_password`; `secrets` sin valores).
- ✅ **Estado remoto desactivado** (`backend.tf` comentado → no puede aplicar contra AWS por accidente).
- ✅ **Workflow plan-only** (no puede hacer `apply`; `plan` gated y comentado).
- ✅ **OIDC no puede provisionar infra** (sólo deploy ECR/ECS).
- ✅ **Nomenclatura consistente** (`${project}-${environment}`).
- ✅ **S3 ↔ StorageProvider** coherente (bucket privado, SSE-KMS, Block Public Access, lifecycle `tenant/`).
- ✅ **RDS MariaDB ↔ PyMySQL/DBUtils** compatible (engine/param group utf8mb4/UTC).
- ✅ **Docker non-root + gevent** compatible con Fargate (salvo la ruta de health, A-2).
- ✅ **CIDRs y nombres aislados** por entorno (10.20/10.30/10.40).
- ✅ **Módulos gated + `try()`** en outputs → sin fallos cuando están desactivados.

---

## E. ORDEN RECOMENDADO DE ACTIVACIÓN FUTURA

Prerrequisitos: instalar AWS CLI + Terraform; cuenta AWS + credenciales/rol; configurar `backend.tf` con
**estado por entorno**; ejecutar `terraform fmt -recursive`.

1. **iam_oidc** (o gestionar el existente) → CI puede autenticarse sin claves.
2. **secrets** → crear contenedores; el propietario rellena valores (resolver A-1 antes).
3. **network** → VPC/subnets/SG/NAT (base de todo lo privado).
4. **s3** → bucket de documentos (activar `STORAGE_BACKEND=s3`).
5. **rds** → MariaDB (aplicar migraciones; validar TLS; resolver B-3). *(depende de network)*
6. **observability** → log groups + alarmas.
7. **ecs** → ECR + cluster + ALB + **task def/service completos** (resolver A-2/A-3) *(depende de network/s3/
   rds/secrets/observability)*.
8. Módulos aún NO incluidos, **necesarios después** (no ahora): **SQS+DLQ** (jobs), **ElastiCache Redis**
   (distribución SSE multi-instancia), **CloudFront + WAF + ACM + Route53** (dominio/HTTPS público).

Revisar SIEMPRE `terraform plan` antes de `apply`, entorno por entorno, empezando por DEV.

## Conclusión

La IaC es **estructuralmente correcta y segura por defecto** (0 recursos, 0 secretos, sin apply posible). Antes
de desplegar hay que resolver **2 bloqueantes** (A-1 nombres de secretos, A-2 ruta de health-check), **aislar
el estado por entorno** (B-1) y completar la **task definition ECS**. Ninguno exige rediseñar la arquitectura.
