# Módulo SECRETS — AWS Secrets Manager + KMS. PREPARADO. Crea los CONTENEDORES de secretos (sin VALORES: los
# rellena el propietario fuera de Terraform). Mapea a SM_SECRET_BACKEND=aws_secrets_manager del secret_manager.
# NUNCA se escriben valores de secretos en este código ni en el estado.

variable "name" { type = string }

resource "aws_kms_key" "secrets" {
  description             = "${var.name} secrets encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

locals {
  # NOMBRES de secretos que la app resuelve por `obtener_secreto(<NOMBRE>)`. Sin valores.
  secret_names = [
    "SMART_MANAGER_JWT_SECRET",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "correo_key", # clave de cifrado de correo (documentos/.correo_key → Secrets Manager)
  ]
}

resource "aws_secretsmanager_secret" "app" {
  for_each   = toset(local.secret_names)
  name       = "${var.name}/${each.value}"
  kms_key_id = aws_kms_key.secrets.arn
  # Sin `aws_secretsmanager_secret_version`: el VALOR lo pone el propietario (consola/CLI), no Terraform.
}

output "kms_key_arn" { value = aws_kms_key.secrets.arn }
output "secret_arns" { value = { for k, s in aws_secretsmanager_secret.app : k => s.arn } }

# Prefijo que la app debe poner en SM_SECRET_PREFIX para resolver estos secretos por su nombre desnudo
# (obtener_secreto("SMART_MANAGER_JWT_SECRET") → "<prefix>SMART_MANAGER_JWT_SECRET"). Casa con `${var.name}/`.
output "secret_prefix" { value = "${var.name}/" }
