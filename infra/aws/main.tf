# ─────────────────────────────────────────────────────────────────────────────
# Smart Manager AI — IaC AWS (raíz). PREPARADA, NO desplegada.
#
# SEGURIDAD: cada módulo se instancia con `count = var.enable_* ? 1 : 0`, todos en `false` por defecto. Por
# tanto `terraform apply` con la configuración por defecto NO crea NINGÚN recurso (0 coste). El propietario
# activa cada capa explícitamente por entorno cuando decida provisionarla. Sin secretos en este código: las
# credenciales/valores se resuelven en runtime vía AWS Secrets Manager / variables de entorno.
#
# Base de datos: MariaDB (Amazon RDS for MariaDB). No se cambia de motor.
# ─────────────────────────────────────────────────────────────────────────────

provider "aws" {
  region = var.aws_region
  # Credenciales por perfil/rol del ejecutor (AWS CLI / OIDC). NUNCA claves en este repo.
  default_tags {
    tags = merge({
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }, var.tags)
  }
}

locals {
  name = "${var.project}-${var.environment}"
}

# ── Red (VPC, subnets públicas/privadas, SG, NAT, VPC endpoints) ──
module "network" {
  source      = "./modules/network"
  count       = var.enable_network ? 1 : 0
  name        = local.name
  vpc_cidr    = var.vpc_cidr
  az_count    = var.az_count
  environment = var.environment
}

# ── RDS MariaDB (privado, cifrado KMS, TLS, backups) ──
module "rds" {
  source                 = "./modules/rds"
  count                  = var.enable_rds ? 1 : 0
  name                   = local.name
  engine_version         = var.rds_engine_version
  instance_class         = var.rds_instance_class
  allocated_storage      = var.rds_allocated_storage
  multi_az               = var.rds_multi_az
  db_name                = var.rds_db_name
  backup_retention_days  = var.rds_backup_retention_days
  vpc_id                 = try(module.network[0].vpc_id, null)
  private_subnet_ids     = try(module.network[0].private_subnet_ids, [])
  app_security_group_id  = try(module.network[0].app_security_group_id, null)
}

# ── S3 (bucket privado de documentos, SSE-KMS, versioning, lifecycle) ──
module "s3" {
  source      = "./modules/s3"
  count       = var.enable_s3 ? 1 : 0
  name        = local.name
  environment = var.environment
}

# ── Secrets Manager + KMS (JWT, OAuth, clave de correo…) ──
module "secrets" {
  source = "./modules/secrets"
  count  = var.enable_secrets ? 1 : 0
  name   = local.name
}

# ── Observabilidad (CloudWatch log groups + alarmas) ──
module "observability" {
  source      = "./modules/observability"
  count       = var.enable_observability ? 1 : 0
  name        = local.name
  environment = var.environment
}

# ── ECR + ECS/Fargate + ALB (compute) ──
module "ecs" {
  source                = "./modules/ecs"
  count                 = var.enable_ecs ? 1 : 0
  name                  = local.name
  aws_region            = var.aws_region
  vpc_id                = try(module.network[0].vpc_id, null)
  public_subnet_ids     = try(module.network[0].public_subnet_ids, [])
  private_subnet_ids    = try(module.network[0].private_subnet_ids, [])
  app_security_group_id = try(module.network[0].app_security_group_id, "")
  log_group_api         = try(module.observability[0].log_group_api, "")
  secret_arns           = try(module.secrets[0].secret_arns, {})
  db_secret_arn         = try(module.rds[0].master_secret_arn, "")
  certificate_arn       = var.ecs_certificate_arn
  container_env         = var.ecs_container_env
}

# ── CI/CD: proveedor OIDC de GitHub + rol de despliegue (mínimo privilegio) ──
module "ci_oidc" {
  source               = "./modules/iam_oidc"
  count                = var.enable_ci_oidc ? 1 : 0
  name                 = local.name
  github_org           = var.github_org
  github_repo          = var.github_repo
  create_oidc_provider = var.ci_create_oidc_provider
}
