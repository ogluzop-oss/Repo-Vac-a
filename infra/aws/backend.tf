# Estado remoto de Terraform (S3 + DynamoDB lock) con AISLAMIENTO POR ENTORNO (B-1).
#
# DESACTIVADO a propósito (no existe el bucket todavía): mientras esté comentado, Terraform usa estado LOCAL y
# NO puede aplicar contra AWS por accidente. NO se crea aquí el bucket ni la tabla DynamoDB (los provisiona el
# propietario una sola vez, fuera de este stack).
#
# Cuando el propietario cree el bucket/tabla de estado, descomentar el bloque VACÍO de abajo (partial config) e
# inicializar CADA ENTORNO con su fichero de backend (key distinta por entorno) → dev/staging/prod NUNCA
# comparten el mismo tfstate:
#
#   terraform init -backend-config=environments/dev.s3.tfbackend
#   terraform init -reconfigure -backend-config=environments/staging.s3.tfbackend
#   terraform init -reconfigure -backend-config=environments/prod.s3.tfbackend
#
# (Alternativa equivalente: `terraform workspace new dev|staging|prod` con una key común; se prefiere la key
#  por entorno por ser explícita y a prueba de errores.)
#
# terraform {
#   backend "s3" {}   # ← configuración PARCIAL: los valores llegan por -backend-config (ficheros por entorno)
# }
#
# Ver: environments/dev.s3.tfbackend.example · staging.s3.tfbackend.example · prod.s3.tfbackend.example
