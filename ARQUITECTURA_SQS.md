# ARQUITECTURA — Amazon SQS (Jobs) (Fase 10)

## Rol

Amazon SQS es la cola preferente para **jobs asíncronos** (worker IA). Reservado a jobs; la distribución de
eventos SSE usa Redis; el dominio usa el Event Bus. Responsabilidades separadas, sin solapamiento.

## Adaptador (`services/jobs/sqs.py`)

- `boto3` perezoso; sin él o sin `SQS_QUEUE_URL` → error explícito (🔵 PREPARADO, no operativo, no simulado).
- `encolar`: `send_message` con `MessageAttributes.id_empresa` (traza de tenant en el transporte).
- `siguiente`: `receive_message` (long-polling ≤ 20 s) → `Job.from_dict` → `delete_message`.
- `profundidad`: `ApproximateNumberOfMessages`.

## Configuración

| Variable | Valor |
|---|---|
| `JOB_QUEUE_BACKEND` | `local` (DEV) / `sqs` (AWS) |
| `SQS_QUEUE_URL` | URL de la cola [EXTERNO] |
| `AWS_REGION` | región |

## Recomendaciones (despliegue)

- Cola estándar o FIFO (FIFO con `MessageGroupId=id_empresa` si se requiere orden por tenant).
- Dead-Letter Queue para jobs fallidos; redrive policy.
- Visibility timeout ≥ duración máxima de un forecast Prophet.
- IAM: la worker role sólo `sqs:ReceiveMessage/DeleteMessage/GetQueueAttributes` sobre esa cola; la API sólo
  `sqs:SendMessage`.

Estado: 🔵 PREPARADO — requiere cola SQS real (🟣 externo).
