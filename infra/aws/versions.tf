# Smart Manager AI — requisitos de Terraform y proveedores (IaC AWS, PREPARADA — NO desplegada).
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
