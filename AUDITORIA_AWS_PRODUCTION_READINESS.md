# AUDITORÍA — AWS PRODUCTION READINESS (Fase 9, SOLO auditoría)

Fecha 2026-07-27. Esta fase **NO despliega ni provisiona nada**. Determina el nivel real de preparación de
Smart Manager AI para una arquitectura AWS empresarial, sobre lo ya construido (8 fases). Regla:
**REUTILIZAR → ADAPTAR → ENDURECER → DESPLEGAR**, nunca reemplazar/duplicar. **No hay AWS provisionado** en
este entorno (0 referencias a `boto3`/SDK AWS en el código; sin credenciales) → todo AWS es 🔵 PREPARADO o
🟣 EXTERNO, jamás 🟢.

## Estado global (3 niveles honestos)

| Nivel | Veredicto |
|---|---|
| **PRODUCTION-READY SOFTWARE** | 🟢 SÍ — backend Flask/gunicorn contenerizado, MariaDB, multi-tenant, seguridad, IA, SSE, observabilidad, backups locales |
| **AWS PRODUCTION-READY** | 🟡 PARCIAL — compatible en su mayoría; requiere adaptaciones acotadas (storage→S3, worker async SSE, non-root, secretos→Secrets Manager) |
| **AWS PRODUCTION-DEPLOYED** | 🔴 NO — no existe infraestructura AWS provisionada |

## Hallazgos de mayor impacto (resumen; detalle en documentos específicos)

1. **Almacenamiento en filesystem** (`documentos/` para PDFs, claves, cachés JSON). En Fargate el filesystem es
   **efímero** → **debe migrar a S3** (privado, por-tenant, URLs firmadas). Es el cambio de mayor alcance.
   Evidencia: `db/documentos.py` (`os.path.join(..., "documentos")`), `utils/cripto.py` (`documentos/.correo_key`).
2. **SSE + gunicorn sync workers** (`-w 4`, sin worker class async). Cada conexión SSE (`while True` + heartbeat
   15s) **bloquea un worker** → no escala. Requiere worker **gevent/gthread** + timeouts de ALB/CloudFront.
3. **Contenedor como root** (Dockerfile sin `USER`). Adaptación de endurecimiento para Fargate.
4. **Secretos en fernet local** (`SM_SECRET_BACKEND=fernet`, `documentos/.correo_key`) con **punto de extensión
   `vault` ya previsto** (degrada). Mapear a **AWS Secrets Manager + KMS**.
5. **Event Bus in-process** (Fase 4). SSE con **1 instancia** funciona; **multi-instancia** requiere broker
   externo (🟣 Redis/NATS) — no introducir ahora.
6. **Prophet CPU-intensivo** (fit ~1-3 s, cmdstan). Ejecuta in-process → conviene **separar worker de IA** en
   ECS + cola de jobs (ya hay `scheduler`/jobs reutilizables).

## Lo que YA es compatible (reutilizable sin cambios de arquitectura)

- **DB**: `db/conexion.py` con **SSL/TLS listo** (`DB_SSL_CA/CERT/KEY`), pool (DBUtils), utf8mb4, autocommit →
  RDS MariaDB directo. Esquema **InnoDB + utf8mb4**, **sin triggers/procedimientos/eventos/SUPER/LOAD DATA** →
  sin fricción de privilegios en RDS.
- **Multi-tenant**: aislamiento por `id_empresa` + `tenant_guard` (404 tablas directas, 0 fugas nuevas) — no se
  toca; se extiende a S3/logs por prefijo de tenant.
- **API**: Flask `/api/v1` con JWT, CORS configurable, rate-limit, HSTS, health `live/ready/version` → ALB/WAF/
  CloudFront compatibles.
- **Observabilidad**: logs JSON (`SM_LOG_JSON`), métricas Prometheus, correlation IDs, OTel degradable →
  CloudWatch por `awslogs`.
- **Backups/DR**: módulos `dr/*` (backup_operacional, pitr, replicacion, storage) → mapear a RDS snapshots + S3.
- **CI**: GitHub Actions (lint/i18n/tests reales sobre MariaDB) → extensible a build→ECR→ECS.

## Conclusión

El software está **preparado para AWS con adaptaciones acotadas y bien delimitadas** (no reescritura). El
siguiente paso (otro prompt) implementará esas adaptaciones **cuando el propietario provisione AWS**. Ver
`MATRIZ_COMPATIBILIDAD_AWS.md`, `PLAN_MIGRACION_AWS.md`, `BLOQUEOS_EXTERNOS_AWS_FASE_9.md` y las auditorías
específicas (RDS, S3, ECS, SSE, Seguridad, CI/CD).
