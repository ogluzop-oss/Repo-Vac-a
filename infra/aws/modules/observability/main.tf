# Módulo OBSERVABILITY — CloudWatch log groups + alarmas base. PREPARADO. Los logs de la app (JSON, stdout)
# se envían con el driver `awslogs` desde la task de ECS a estos log groups.

variable "name" { type = string }
variable "environment" { type = string }
variable "log_retention_days" {
  type    = number
  default = 30
}
variable "alarm_sns_topic_arn" {
  description = "SNS de alarmas (opcional). [EXTERNO]"
  type        = string
  default     = ""
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/${var.name}/api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/${var.name}/worker-ia"
  retention_in_days = var.log_retention_days
}

# Alarmas base (se enganchan a los recursos reales cuando ECS/RDS existan). Plantilla mínima.
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.name}-api-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_sns_topic_arn == "" ? [] : [var.alarm_sns_topic_arn]
  # dimensions (LoadBalancer/TargetGroup) se añaden al integrar con el módulo ecs.
}

# Identificadores opcionales de recursos reales (se conectan al activar ecs/rds). Vacío → alarma no creada.
variable "db_instance_id" {
  type    = string
  default = ""
}
variable "ecs_cluster_name" {
  type    = string
  default = ""
}
variable "ecs_service_name" {
  type    = string
  default = ""
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  count               = var.db_instance_id == "" ? 0 : 1
  alarm_name          = "${var.name}-rds-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  dimensions          = { DBInstanceIdentifier = var.db_instance_id }
  alarm_actions       = var.alarm_sns_topic_arn == "" ? [] : [var.alarm_sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "ecs_cpu" {
  count               = var.ecs_service_name == "" ? 0 : 1
  alarm_name          = "${var.name}-ecs-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 85
  treat_missing_data  = "notBreaching"
  dimensions          = { ClusterName = var.ecs_cluster_name, ServiceName = var.ecs_service_name }
  alarm_actions       = var.alarm_sns_topic_arn == "" ? [] : [var.alarm_sns_topic_arn]
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.name}-overview"
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "text", x = 0, y = 0, width = 24, height = 2,
        properties = { markdown = "# ${var.name} — ${var.environment}\nDashboard base (ALB 5xx, ECS CPU, RDS CPU)." }
      }
    ]
  })
}

output "log_group_api" { value = aws_cloudwatch_log_group.api.name }
output "log_group_worker" { value = aws_cloudwatch_log_group.worker.name }
output "dashboard_name" { value = aws_cloudwatch_dashboard.main.dashboard_name }
