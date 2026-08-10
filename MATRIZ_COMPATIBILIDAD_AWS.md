# MATRIZ DE COMPATIBILIDAD AWS — Smart Manager AI (Fase 9)

Estados: 🟢 LISTO · 🟡 REQUIERE ADAPTACIÓN · 🔵 PREPARADO (software) · 🟣 EXTERNO (infra por provisionar) ·
🔴 NO COMPATIBLE. **Nada está 🟢 "verificado en AWS real"** porque AWS no está provisionado.

| Componente | Estado | AWS objetivo | Acción necesaria |
|---|---|---|---|
| Docker | 🟡 | ECS/Fargate | Añadir `USER` no-root, worker gunicorn async (SSE), `.dockerignore`, quitar escrituras a filesystem (S3), fijar ruta de healthcheck |
| MariaDB | 🟢/🟡 | RDS MariaDB | Compatible (InnoDB/utf8mb4, sin triggers/procs/SUPER, SSL listo); adaptar: parameter group utf8mb4, `rds-ca` bundle, Multi-AZ (externo) |
| Storage | 🟡 | S3 | Migrar `documentos/` (PDF/claves/cachés) a S3 privado por-tenant + URLs firmadas; abstraer capa de ficheros |
| Secrets | 🔵 | Secrets Manager | Implementar backend `vault`/AWS en `secret_manager` (punto de extensión ya existe); mover `.correo_key`, JWT, DB, OAuth |
| Cifrado | 🔵 | KMS | Claves de datos vía KMS; hoy fernet local (degradable) |
| DNS | 🟣 | Route 53 | Registrar dominio y zona (propietario) |
| TLS | 🟣 | ACM | Emitir certificados (propietario, requiere dominio) |
| CDN | 🟡 | CloudFront | Distribución con política SSE (no-buffer) + OAC a S3 |
| WAF | 🔵 | AWS WAF | Reglas gestionadas + rate-based; app ya tiene rate-limit propio |
| Load Balancer | 🟡 | ALB | Target group ECS, health check path, idle timeout ≥ heartbeat SSE |
| Runtime | 🟡 | ECS Fargate | Task def (api + worker-ia), autoscaling, secrets desde Secrets Manager |
| CI/CD | 🔵 | ECR/ECS | Extender Actions: OIDC→ECR build→ECS deploy→smoke→approval→prod |
| Observabilidad | 🔵 | CloudWatch | `awslogs` driver + métricas; sistema propio se conserva |
| Auditoría | 🟢 (app) / 🔵 (AWS) | CloudTrail | Auditoría de negocio ya existe (`log_auditoria`); CloudTrail cubre el plano AWS |
| Red | 🟣 | VPC | VPC/subnets/SG/NAT (propietario/IaC) |
| IA | 🔵 | ECS/Workers | Separar `worker-ia` (Prophet) + cola; modelos ya se persisten en RDS |
| SSE | 🟡 | ALB/CloudFront | Worker async + timeouts + no-buffer; 1 instancia OK, multi-instancia 🟣 broker |
| Backups | 🔵 | RDS/S3 | RDS automated backups/snapshots + S3 versioning; `dr/*` reutilizable |
| DR | 🟡/🟣 | Multi-AZ/DR | Multi-AZ + cross-region (externo); simulacro real pendiente |

## Resumen

- **🟢 LISTO**: MariaDB (esquema/driver), auditoría de negocio.
- **🟡 ADAPTACIÓN acotada**: Docker, Storage, CloudFront, ALB, Fargate, SSE, DR.
- **🔵 PREPARADO (software)**: Secrets Manager, KMS, WAF, CI/CD, Observabilidad, IA worker, Backups.
- **🟣 EXTERNO**: Route 53, ACM, VPC, Multi-AZ/cross-region (provisión del propietario).
- **🔴 NO COMPATIBLE**: ninguno.
