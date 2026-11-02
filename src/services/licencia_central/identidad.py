"""
Identidad de instalación (Fase 1 del proyecto de infraestructura central — ver plan
`hazy-riding-aurora`). `installation_id` es un UUID real, generado UNA sola vez por instalación y
persistido en un JSON local (mismo patrón per-install que `config_edicion.json`/
`config_onboarding.json` de `services/verticales.py`/`services/onboarding.py`): sobrevive a
reinicios y actualizaciones del software, pero es único por máquina/instalación.

Es DISTINTO y no sustituye a `id_empresa` (`src/db/conexion.py::EMPRESA_DEFAULT_ID`, compartido
entre instalaciones y usado para el aislamiento de datos LOCAL) — `installation_id` es el único
identificador que el servidor central llegará a conocer; no se usa en ninguna consulta local.
"""

import json
import logging
import os
import uuid

logger = logging.getLogger("licencia_central.identidad")

# Mismo patrón que `services/verticales.py::RUTA_CONFIG`: un nivel más profundo (services/
# licencia_central/ en vez de services/), así que sube un nivel extra para llegar a la raíz.
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RUTA_CONFIG = os.path.join(_RAIZ, "config_instalacion.json")


def _leer() -> dict:
    try:
        with open(RUTA_CONFIG, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def _escribir(datos: dict) -> bool:
    try:
        with open(RUTA_CONFIG, "w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error("No se pudo persistir %s: %s", RUTA_CONFIG, e)
        return False


def obtener_installation_id() -> str:
    """Devuelve el `installation_id` de esta instalación, generándolo (UUID4) la primera vez que
    se llama. Idempotente: llamadas posteriores devuelven siempre el mismo valor."""
    datos = _leer()
    iid = datos.get("installation_id")
    if iid:
        return iid
    nuevo = str(uuid.uuid4())
    datos["installation_id"] = nuevo
    if _escribir(datos):
        logger.info("Nuevo installation_id generado: %s", nuevo)
    return nuevo


def activado() -> bool:
    """¿Esta instalación ya canjeó su código de activación por credenciales del servidor central?
    (ver `licencia_central.cliente.activar`/`licencia_central.credenciales.guardar`, que son
    quienes marcan `activado=True` al guardar las credenciales)."""
    return bool(_leer().get("activado"))
