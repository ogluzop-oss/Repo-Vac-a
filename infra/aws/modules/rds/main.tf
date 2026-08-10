# Módulo RDS — Amazon RDS for MariaDB (privado, cifrado, TLS, backups). PREPARADO.
# La contraseña del usuario master la gestiona AWS en Secrets Manager (manage_master_user_password) → NUNCA
# aparece en el código ni en el estado en claro. Parameter group utf8mb4/UTC compatible con la app.

variable "name" { type = string }
variable "engine_version" { type = string }
variable "instance_class" { type = string }
variable "allocated_storage" { type = number }
variable "multi_az" { type = bool }
variable "db_name" { type = string }
variable "backup_retention_days" { type = number }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "app_security_group_id" { type = string }

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-db-subnets"
  subnet_ids = var.private_subnet_ids
  tags       = { Name = "${var.name}-db-subnets" }
}

# SG de RDS: sólo acepta 3306 desde el SG de la app (nunca acceso público).
resource "aws_security_group" "rds" {
  name        = "${var.name}-rds-sg"
  description = "RDS MariaDB - solo desde la app"
  vpc_id      = var.vpc_id
  ingress {
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [var.app_security_group_id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${var.name}-rds-sg" }
}

resource "aws_kms_key" "rds" {
  description             = "${var.name} RDS encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_db_parameter_group" "this" {
  name   = "${var.name}-mariadb"
  family = "mariadb11.4"
  parameter {
    name  = "character_set_server"
    value = "utf8mb4"
  }
  parameter {
    name  = "collation_server"
    value = "utf8mb4_unicode_ci"
  }
  parameter {
    name  = "time_zone"
    value = "UTC"
  }
  # Exige TLS: RDS rechaza conexiones sin cifrar. La app DEBE conectar con TLS → fijar DB_SSL_CA (bundle
  # rds-combined-ca). PyMySQL/DBUtils lo soportan: db/conexion.py añade DB_CONFIG["ssl"] cuando DB_SSL_CA
  # está presente (ssl={"ca": ...}). Sin DB_SSL_CA, la conexión fallará (comportamiento seguro y deseado).
  parameter {
    name  = "require_secure_transport"
    value = "ON"
  }
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name}-mariadb"
  engine         = "mariadb"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.allocated_storage * 4
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = aws_kms_key.rds.arn

  db_name  = var.db_name
  username = "smart_admin"
  # Contraseña gestionada por AWS en Secrets Manager (sin secreto en el código/estado).
  manage_master_user_password = true

  multi_az               = var.multi_az
  publicly_accessible    = false
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.this.name

  backup_retention_period    = var.backup_retention_days
  copy_tags_to_snapshot      = true
  auto_minor_version_upgrade = true
  deletion_protection        = true
  skip_final_snapshot        = false
  final_snapshot_identifier  = "${var.name}-mariadb-final"

  # TLS obligatorio a nivel de app (DB_SSL_CA con el bundle rds-combined-ca).
  tags = { Name = "${var.name}-mariadb" }
}

output "endpoint" { value = aws_db_instance.this.address }
output "port" { value = aws_db_instance.this.port }
output "master_secret_arn" { value = aws_db_instance.this.master_user_secret[0].secret_arn }
output "security_group_id" { value = aws_security_group.rds.id }
