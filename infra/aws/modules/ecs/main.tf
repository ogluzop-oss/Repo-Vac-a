# Módulo ECS — ECR + ECS/Fargate (servicios api y worker-ia) + ALB. PREPARADO (esqueleto ampliable).
# El contenedor arranca gunicorn+gevent (SSE) como usuario non-root (Dockerfile ya endurecido). Los secretos
# se inyectan por `secrets` de la task definition (ARNs de Secrets Manager), nunca en `environment` en claro.

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "container_port" {
  type    = number
  default = 8000
}
variable "desired_count" {
  type    = number
  default = 2
}
variable "aws_region" {
  type    = string
  default = "eu-west-1"
}
variable "app_security_group_id" {
  type    = string
  default = ""
}
variable "image_tag" {
  type    = string
  default = "bootstrap" # sustituido por el SHA del commit en el pipeline de despliegue
}
variable "cpu" {
  type    = number
  default = 512
}
variable "memory" {
  type    = number
  default = 1024
}
variable "min_capacity" {
  type    = number
  default = 2
}
variable "max_capacity" {
  type    = number
  default = 6
}
variable "log_group_api" {
  type    = string
  default = ""
}
# name(env var) → ARN de Secrets Manager. Se inyectan como `secrets` (valueFrom), nunca en claro.
variable "secret_arns" {
  type    = map(string)
  default = {}
}
# Secreto gestionado de RDS (DB_PASSWORD). Formato valueFrom: "<arn>:password::".
variable "db_secret_arn" {
  type    = string
  default = ""
}
# Certificado ACM para el listener HTTPS. Vacío → sólo HTTP (ACM se añade en la fase de dominio).
variable "certificate_arn" {
  type    = string
  default = ""
}
# Variables de entorno del contenedor (STORAGE_BACKEND=s3, SM_SECRET_BACKEND=..., etc.).
variable "container_env" {
  type    = map(string)
  default = {}
}

resource "aws_ecr_repository" "app" {
  name                 = "${var.name}-backend"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecs_cluster" "this" {
  name = "${var.name}-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# SG del ALB (443 público) y regla para que el ALB alcance la app.
resource "aws_security_group" "alb" {
  name        = "${var.name}-alb-sg"
  description = "ALB publico HTTPS"
  vpc_id      = var.vpc_id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${var.name}-alb-sg" }
}

resource "aws_lb" "this" {
  name               = "${var.name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids
  idle_timeout       = 120 # > heartbeat SSE (15s) para no cortar conexiones largas
}

resource "aws_lb_target_group" "app" {
  name        = "${var.name}-tg"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"
  health_check {
    path                = "/api/v1/live"
    matcher             = "200"
    interval            = 15
    healthy_threshold   = 2
    unhealthy_threshold = 5
  }
}

# ── Listeners: HTTP (80) siempre; HTTPS (443) sólo si hay certificado ACM (fase de dominio) ──
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    # Si hay HTTPS, redirige 80→443; si no, reenvía al target group.
    type = var.certificate_arn == "" ? "forward" : "redirect"
    dynamic "redirect" {
      for_each = var.certificate_arn == "" ? [] : [1]
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
    target_group_arn = var.certificate_arn == "" ? aws_lb_target_group.app.arn : null
  }
}

resource "aws_lb_listener" "https" {
  count             = var.certificate_arn == "" ? 0 : 1
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

# Ingress al SG de la app desde el ALB (puerto del contenedor).
resource "aws_security_group_rule" "alb_to_app" {
  count                    = var.app_security_group_id == "" ? 0 : 1
  type                     = "ingress"
  from_port                = var.container_port
  to_port                  = var.container_port
  protocol                 = "tcp"
  security_group_id        = var.app_security_group_id
  source_security_group_id = aws_security_group.alb.id
}

# ── IAM: execution role (arranque: pull ECR, logs, leer secretos) y task role (permisos de la app) ──
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-ecs-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Permiso de arranque para LEER los secretos concretos inyectados (mínimo privilegio).
data "aws_iam_policy_document" "execution_secrets" {
  count = length(var.secret_arns) > 0 || var.db_secret_arn != "" ? 1 : 0
  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = compact(concat(values(var.secret_arns), [var.db_secret_arn]))
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  count  = length(data.aws_iam_policy_document.execution_secrets) > 0 ? 1 : 0
  name   = "${var.name}-exec-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets[0].json
}

resource "aws_iam_role" "task" {
  name               = "${var.name}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# ── Task definition (api) ──
resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
    essential = true
    portMappings = [{
      containerPort = var.container_port
      protocol      = "tcp"
    }]
    environment = [for k, v in var.container_env : { name = k, value = v }]
    secrets = concat(
      [for k, arn in var.secret_arns : { name = k, valueFrom = arn }],
      var.db_secret_arn == "" ? [] : [{ name = "DB_PASSWORD", valueFrom = "${var.db_secret_arn}:password::" }]
    )
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = var.log_group_api == "" ? "/${var.name}/api" : var.log_group_api
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }
  }])
}

# ── Service (Fargate) ──
resource "aws_ecs_service" "api" {
  name            = "${var.name}-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = compact([var.app_security_group_id])
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "api"
    container_port   = var.container_port
  }
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  depends_on                         = [aws_lb_listener.http]
}

# ── Auto Scaling (CPU) ──
resource "aws_appautoscaling_target" "api" {
  max_capacity       = var.max_capacity
  min_capacity       = var.min_capacity
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "${var.name}-api-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 65
  }
}

output "ecr_repository_url" { value = aws_ecr_repository.app.repository_url }
output "task_definition_arn" { value = aws_ecs_task_definition.api.arn }
output "service_name" { value = aws_ecs_service.api.name }
output "execution_role_arn" { value = aws_iam_role.execution.arn }
output "task_role_arn" { value = aws_iam_role.task.arn }
output "cluster_arn" { value = aws_ecs_cluster.this.arn }
output "alb_dns_name" { value = aws_lb.this.dns_name }
output "target_group_arn" { value = aws_lb_target_group.app.arn }
