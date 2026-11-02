"""
Resolución del gateway RFID activo — API-First, sin PyQt.

Único punto que decide "¿con qué lector hablamos ahora mismo?": lee `db.rfid_hardware.
obtener_config` (empresa + centro activo) e instancia `LectorZebraGateway` ya configurado. Degrada
a modo SIMULADO automáticamente en cualquier caso dudoso (sin fila de config, `modo='fisico'` pero
sin IP guardada) — nunca intenta una conexión real "a ciegas" sin una IP explícita."""

import logging

logger = logging.getLogger("rfid.hardware")


def resolver_gateway(id_empresa, id_centro=None):
    """`LectorZebraGateway` listo para usar, con la config real de (empresa, centro) si existe.
    Siempre devuelve una instancia utilizable (nunca None): sin config → simulado con la IP de
    ejemplo por defecto, exactamente como se comportaba el gateway antes de esta tarea."""
    from src.utils.rfid_gateway import LectorZebraGateway

    try:
        from src.db import rfid_hardware as rfid_db
        cfg = rfid_db.obtener_config(id_empresa, id_centro) if id_empresa else {}
    except Exception as e:
        logger.error("resolver_gateway: no se pudo leer la config (%s)", e)
        cfg = {}

    modo = (cfg.get("modo") or "simulado").strip().lower()
    ip = (cfg.get("ip") or "").strip() or None
    puerto = cfg.get("puerto") or 5084

    if modo == "fisico" and not ip:
        logger.warning("resolver_gateway: modo 'fisico' sin IP configurada — degradando a simulado "
                       "(nunca se conecta a ciegas).")
        modo = "simulado"

    modo_simulado = modo != "fisico"
    return LectorZebraGateway(ip=ip or "192.168.0.100", puerto=puerto, modo_simulado=modo_simulado)
