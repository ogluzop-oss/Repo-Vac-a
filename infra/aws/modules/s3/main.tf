# Módulo S3 — bucket PRIVADO de documentos (SSE-KMS, versioning, lifecycle, Block Public Access). PREPARADO.
# Mapea a STORAGE_BACKEND=s3 + S3_BUCKET/S3_SSE/S3_KMS_KEY_ID del backend. Aislamiento por tenant vía prefijo
# `tenant/{id_empresa}/...` (lo aplica la app) + IAM del rol de la task.

variable "name" { type = string }
variable "environment" { type = string }

resource "aws_kms_key" "docs" {
  description             = "${var.name} S3 documents encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_s3_bucket" "docs" {
  bucket = "${var.name}-documentos"
  tags   = { Name = "${var.name}-documentos", Environment = var.environment }
}

resource "aws_s3_bucket_public_access_block" "docs" {
  bucket                  = aws_s3_bucket.docs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "docs" {
  bucket = aws_s3_bucket.docs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "docs" {
  bucket = aws_s3_bucket.docs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.docs.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "docs" {
  bucket = aws_s3_bucket.docs.id
  rule {
    id     = "transicion-historicos"
    status = "Enabled"
    filter {
      prefix = "tenant/"
    }
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
    noncurrent_version_expiration {
      noncurrent_days = 365
    }
  }
}

output "bucket_name" { value = aws_s3_bucket.docs.id }
output "bucket_arn" { value = aws_s3_bucket.docs.arn }
output "kms_key_arn" { value = aws_kms_key.docs.arn }
