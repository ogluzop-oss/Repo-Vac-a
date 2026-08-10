# Variables globales de la IaC. Sin valores por defecto sensibles; nada de secretos. Los valores por entorno
# se pasan con `-var-file=environments/<env>.tfvars` (ver ejemplos *.tfvars.example).

variable "aws_region" {
  description = "Región AWS objetivo (p. ej. eu-west-1). [EXTERNO]"
  type        = string
  default     = "eu-west-1"
}

variable "environment" {
  description = "Entorno lógico: dev | staging | production."
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "environment debe ser dev, staging o production."
  }
}

variable "project" {
  description = "Prefijo de nombres de recursos."
  type        = string
  default     = "smart-manager"
}

variable "tags" {
  description = "Etiquetas comunes."
  type        = map(string)
  default     = {}
}

# ── Interruptores de despliegue (SEGURIDAD): todo en false por defecto → `apply` NO crea nada.
# El propietario activa cada módulo explícitamente cuando decida provisionarlo. Ver README.
variable "enable_network" {
  type    = bool
  default = false
}
variable "enable_rds" {
  type    = bool
  default = false
}
variable "enable_s3" {
  type    = bool
  default = false
}
variable "enable_secrets" {
  type    = bool
  default = false
}
variable "enable_observability" {
  type    = bool
  default = false
}
variable "enable_ecs" {
  type    = bool
  default = false
}
variable "enable_ci_oidc" {
  type    = bool
  default = false
}

# ── Red ──
variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}
variable "az_count" {
  type    = number
  default = 2
}

# ── RDS MariaDB ──
variable "rds_engine_version" {
  type    = string
  default = "11.4" # MariaDB
}
variable "rds_instance_class" {
  type    = string
  default = "db.t3.medium"
}
variable "rds_allocated_storage" {
  type    = number
  default = 20
}
variable "rds_multi_az" {
  type    = bool
  default = false # true en producción
}
variable "rds_db_name" {
  type    = string
  default = "smart_manager"
}
variable "rds_backup_retention_days" {
  type    = number
  default = 7
}

# ── CI/CD OIDC (GitHub Actions) ──
variable "github_org" {
  description = "Organización/usuario de GitHub para el trust de OIDC. [EXTERNO]"
  type        = string
  default     = "<github-org>"
}
variable "github_repo" {
  description = "Repositorio para el trust de OIDC. [EXTERNO]"
  type        = string
  default     = "<github-repo>"
}

variable "ci_create_oidc_provider" {
  description = "Crear el proveedor OIDC de GitHub (true) o referenciar el existente si la cuenta ya lo tiene (false). Evita colisiones sin `terraform import`."
  type        = bool
  default     = true
}

# ── ECS/ALB ──
variable "ecs_certificate_arn" {
  description = "ARN del certificado ACM para el listener HTTPS del ALB. Vacío → sólo HTTP (ACM = fase de dominio). [EXTERNO]"
  type        = string
  default     = ""
}
variable "ecs_container_env" {
  description = "Variables de entorno del contenedor (p. ej. STORAGE_BACKEND=s3, SM_SECRET_BACKEND=aws_secrets_manager). Sin secretos: los secretos van por Secrets Manager."
  type        = map(string)
  default     = {}
}
