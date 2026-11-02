"""
Cliente HTTP de "llamar a casa" (Fase 3). Llamadas salientes al servidor central de licencias
(`src/backend_central/`), mismo patrón defensivo que `services/fiscal/emisores/verifactu_aeat.py`:
timeout corto, nunca lanza, siempre degrada con gracia — sin red o con el servidor central caído,
la instalación sigue funcionando con el último estado local conocido (ver `sincronizacion.py`).

`SMART_MANAGER_LICENCIA_URL` (variable de entorno) apunta al servidor central; sin ella, activar
y verificar son no-op (instalación no adherida a licenciamiento central, comportamiento legacy).
"""

import logging
import os

logger = logging.getLogger("licencia_central.cliente")

_TIMEOUT_SEG = 8


def _url_base() -> str:
    return (os.getenv("SMART_MANAGER_LICENCIA_URL") or "").rstrip("/")


def activar(codigo_activacion: str, nombre_empresa: str) -> dict:
    """Canjea un código de activación por credenciales M2M para esta instalación (llamada única,
    del asistente de activación). En éxito ya ha guardado las credenciales localmente cifradas."""
    base = _url_base()
    if not base:
        return {"ok": False, "error": "No hay servidor central configurado (SMART_MANAGER_LICENCIA_URL)."}
    if not codigo_activacion or not nombre_empresa:
        return {"ok": False, "error": "Faltan datos."}

    from src.services.licencia_central import identidad
    installation_id = identidad.obtener_installation_id()
    try:
        import requests
        r = requests.post(
            f"{base}/central/activar",
            json={"codigo_activacion": codigo_activacion.strip(), "installation_id": installation_id,
                 "nombre_empresa": nombre_empresa.strip()},
            timeout=_TIMEOUT_SEG,
        )
        datos = r.json()
    except Exception as e:
        logger.error("activar: no se pudo contactar con el servidor central (%s)", e)
        return {"ok": False, "error": "No se pudo contactar con el servidor central. Comprueba tu conexión."}

    if r.status_code != 200 or not datos.get("ok"):
        return {"ok": False, "error": datos.get("error") or f"Error del servidor (HTTP {r.status_code})."}

    from src.services.licencia_central import credenciales
    if not credenciales.guardar(datos["client_id"], datos["client_secret"]):
        return {"ok": False, "error": "No se pudieron guardar las credenciales localmente."}
    logger.info("Instalación activada contra el servidor central.")
    return {"ok": True}


def verificar_licencia() -> dict | None:
    """Llamada periódica ('llamar a casa'). Devuelve la respuesta del servidor central
    ({plan, estado, proximo_cobro}) o None si no se pudo verificar (sin servidor configurado,
    instalación no activada, offline, o el servidor central rechazó la petición). `None` NUNCA
    debe interpretarse como "sin licencia" — solo como "no se sabe, por ahora" (ver
    `sincronizacion.revisar_periodo_gracia` para el único mecanismo que sí actúa tras un `None`
    prolongado)."""
    base = _url_base()
    if not base:
        return None
    from src.services.licencia_central import credenciales
    cred = credenciales.obtener()
    if not cred:
        return None
    client_id, client_secret = cred

    try:
        import requests
        r_tok = requests.post(
            f"{base}/central/oauth/token",
            json={"client_id": client_id, "client_secret": client_secret},
            timeout=_TIMEOUT_SEG,
        )
        tok = r_tok.json()
        if r_tok.status_code != 200 or not tok.get("ok"):
            logger.warning("No se pudo obtener token del servidor central: %s", tok.get("error"))
            return None

        r_ver = requests.get(
            f"{base}/central/licencia/verificar",
            headers={"Authorization": f"Bearer {tok['access_token']}"},
            timeout=_TIMEOUT_SEG,
        )
        ver = r_ver.json()
        if r_ver.status_code != 200 or not ver.get("ok"):
            logger.warning("Verificación de licencia rechazada: %s", ver.get("error"))
            return None
        return ver
    except Exception as e:
        logger.debug("verificar_licencia: sin conexión con el servidor central (%s)", e)
        return None
