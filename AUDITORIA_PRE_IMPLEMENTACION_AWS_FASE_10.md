# AUDITORÍA PRE-IMPLEMENTACIÓN AWS (Fase 10, Fase 0)

Fecha 2026-07-27. Verificación del estado real ANTES de implementar. El código real tiene prioridad sobre la
documentación. Baseline de regresión confirmado: **638 passed, 1 skipped, 0 failed**.

## Confirmación de los hallazgos de la Fase 9 (siguen válidos)

| Hallazgo Fase 9 | ¿Sigue válido? | Evidencia |
|---|---|---|
| Storage en filesystem (`documentos/`) | ✅ | `db/documentos.py`, `utils/cripto.py` (`documentos/.correo_key`) |
| SSE + gunicorn **sync** workers | ✅ | Dockerfile `gunicorn -w 4` (sin worker-class); `realtime.py` `while True` + heartbeat |
| Contenedor como **root** | ✅ | Dockerfile sin `USER` |
| Secret Manager con extensión `vault` | ✅ | `secret_manager._backend()` fernet/vault |
| Event Bus **in-process**, `set_distribucion` previsto pero NO reenvía | ✅ | `realtime.set_distribucion` guardaba el adaptador pero `_on_event` no lo invocaba |
| 0 `boto3` en el código | ✅ | ningún import real de AWS SDK |
| RDS-compatible (InnoDB/utf8mb4, sin triggers/procs/SUPER) | ✅ | `db/conexion.py` SSL/pool; esquema InnoDB |

## Ajuste respecto a la documentación

- El punto de extensión `set_distribucion` existía pero `_on_event` **no propagaba** los eventos locales al
  adaptador → esta fase lo cablea (aditivo, sin cambiar el comportamiento single-instance por defecto).

## Alcance de esta fase (software AWS-ready, sin desplegar)

Implementar abstracciones con **backend local por defecto** y **backend AWS preparado/degradable** (boto3
perezoso), sin simular AWS operativo, sin duplicar sistemas, sin romper las fases previas:
storage (local/S3), secretos (fernet/vault/AWS), distribución de eventos (local/inprocess/Redis), cola de jobs
(local/SQS) + worker de IA, Docker hardening, config, IaC skeleton.

**Regla de detención**: boto3/AWS no están disponibles → los backends AWS quedan 🔵 PREPARADOS (degradables),
nunca 🟢. No se provisiona ni se simula nada.
