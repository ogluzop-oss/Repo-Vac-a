# Salidas informativas. Con todos los `enable_*` en false, son null/vacías (nada provisionado).

output "estado" {
  value = "IaC PREPARADA (no aplicada). Activa módulos con enable_* por entorno. Nada desplegado por defecto."
}

output "vpc_id" {
  value = try(module.network[0].vpc_id, null)
}

output "rds_endpoint" {
  description = "Endpoint RDS (null si enable_rds=false)."
  value       = try(module.rds[0].endpoint, null)
}

output "s3_bucket" {
  value = try(module.s3[0].bucket_name, null)
}

output "ecr_repo_url" {
  value = try(module.ecs[0].ecr_repository_url, null)
}

output "ci_deploy_role_arn" {
  value = try(module.ci_oidc[0].deploy_role_arn, null)
}
