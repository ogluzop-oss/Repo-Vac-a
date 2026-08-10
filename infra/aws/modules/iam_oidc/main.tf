# Módulo IAM_OIDC — proveedor OIDC de GitHub Actions + rol de despliegue de CI/CD (mínimo privilegio).
# PREPARADO. Permite que el pipeline se autentique SIN claves estáticas (OIDC). El rol se restringe al
# repositorio indicado. Los permisos concretos (ECR/ECS) se acotan; sin `AdministratorAccess`.

variable "name" { type = string }
variable "github_org" { type = string }
variable "github_repo" { type = string }

# Colisión de proveedor OIDC (B-2): AWS permite UN solo proveedor por URL y cuenta. Si la cuenta YA tiene el
# proveedor de GitHub, poner `create_oidc_provider = false` para REFERENCIAR el existente (data source) en vez
# de crear uno nuevo. Sin `terraform import`; sin crear/modificar nada mientras el módulo esté desactivado.
variable "create_oidc_provider" {
  type    = bool
  default = true
}

data "aws_caller_identity" "current" {}

# Se crea SÓLO si create_oidc_provider = true.
resource "aws_iam_openid_connect_provider" "github" {
  count           = var.create_oidc_provider ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# Referencia al proveedor EXISTENTE si create_oidc_provider = false (no lo crea, no lo importa).
data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      # Sólo ramas/entornos de ESTE repositorio.
      values = ["repo:${var.github_org}/${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "${var.name}-ci-deploy"
  assume_role_policy = data.aws_iam_policy_document.trust.json
}

# Política de despliegue acotada (ECR push + ECS update). Ampliable según necesidad; sin comodines de recurso
# innecesarios cuando se conozcan los ARNs reales.
data "aws_iam_policy_document" "deploy" {
  statement {
    sid    = "EcrPushPull"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
    ]
    resources = ["*"] # acotar al ARN del repo ECR cuando exista
  }
  statement {
    sid    = "EcsDeploy"
    effect = "Allow"
    actions = [
      "ecs:DescribeServices",
      "ecs:DescribeTaskDefinition",
      "ecs:RegisterTaskDefinition",
      "ecs:UpdateService",
    ]
    resources = ["*"] # acotar al cluster/servicio cuando exista
  }
  statement {
    sid       = "PassExecutionRole"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.name}-*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "${var.name}-ci-deploy-policy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

output "deploy_role_arn" { value = aws_iam_role.deploy.arn }
output "oidc_provider_arn" { value = local.oidc_provider_arn }
