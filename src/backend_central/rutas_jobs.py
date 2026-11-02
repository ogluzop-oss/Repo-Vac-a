"""
Rutas de TAREAS PERIÓDICAS del servidor central: dunning (recuperación de impagos) y facturación
automática. Reutilizan `services.saas.dunning`/`services.saas.facturacion_automatica` (ya
existían, pensados para el Scheduler LOCAL del escritorio — aquí se exponen como endpoint HTTP en
vez de un job del Scheduler, porque el servidor central no tiene escritorio ni `services.scheduler`;
un cron/tarea programada EXTERNA (systemd timer, EventBridge, CronJob de K8s — según cómo se
despliegue en la Fase 5) las dispara periódicamente. No se crea ningún motor de cobro/dunning nuevo.

Autenticación: secreto compartido simple (`CENTRAL_JOBS_SECRET`), NO el OAuth2 de clientes — estas
rutas nunca las llama una instalación de cliente, solo el programador de tareas del propio
servidor. Mismo patrón de cabecera que la clave maestra M2M ya existente en `src/api/security.py`
(`X-API-Key`), pero con su PROPIO secreto — dominios de seguridad distintos (no se reutiliza
`API_MASTER_KEY`, que es del backend local, para no compartir un secreto entre dos superficies).
"""

import logging
import os

logger = logging.getLogger("backend_central.rutas_jobs")


def _autorizado(request) -> bool:
    secreto = os.getenv("CENTRAL_JOBS_SECRET")
    return bool(secreto) and request.headers.get("X-API-Key") == secreto


def crear_blueprint():
    from flask import Blueprint, jsonify, request

    bp = Blueprint("jobs_central", __name__, url_prefix="/central/jobs")

    @bp.post("/dunning")
    def dunning():
        if not _autorizado(request):
            return jsonify({"ok": False, "error": "No autorizado."}), 401
        from src.services.saas import dunning as _D
        r = _D.procesar_todas()
        logger.info("Job dunning ejecutado: %s", r)
        return jsonify({"ok": True, **r})

    @bp.post("/facturacion")
    def facturacion():
        if not _autorizado(request):
            return jsonify({"ok": False, "error": "No autorizado."}), 401
        from src.services.saas import facturacion_automatica as _F
        r = _F.facturar_vencidas()
        logger.info("Job facturación automática ejecutado: %s", r)
        return jsonify({"ok": True, **r})

    return bp
