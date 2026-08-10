"""
Interruptor MAESTRO de intención AWS (Fase 15). `AWS_ENABLED` (por defecto false) indica si la aplicación debe
operar con servicios AWS. Es ADVISORY: no fuerza backends por sí solo (los backends se eligen con
STORAGE_BACKEND/SM_SECRET_BACKEND/JOB_QUEUE_BACKEND, todos con default local). Sirve para que el código futuro
que integre AWS pueda condicionarse a un único flag y para verificar en tests que, por defecto, AWS está OFF.
"""

import os


def aws_enabled() -> bool:
    return os.getenv("AWS_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
