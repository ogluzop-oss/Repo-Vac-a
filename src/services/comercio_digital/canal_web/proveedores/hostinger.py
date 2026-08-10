"""
Canal Web · Proveedor **Hostinger** (Fase WEB-02) — PREPARADO, NO operativo. Hostinger es el proveedor OFICIAL
para crear páginas web desde cero. Aquí sólo se deja la abstracción/contrato: NO se implementan API, OAuth,
autenticación ni sincronización. `disponible()` = False hasta que exista integración real + credenciales
(vía Secret Manager). Ninguna llamada externa se realiza.
"""

import logging
import os

from src.services.comercio_digital.canal_web.proveedores.base import (
    EspecificacionWeb, ProveedorWeb)

logger = logging.getLogger("canal_web.proveedores.hostinger")


class HostingerProvider(ProveedorWeb):
    clave = "hostinger"
    nombre = "Hostinger"
    oficial = True

    def disponible(self) -> bool:
        # PREPARADO: sólo estaría disponible con integración real + credenciales (futuro). Hoy: False.
        # (Se deja el punto de comprobación; nunca expone/pide secretos aquí.)
        return bool(os.getenv("HOSTINGER_ENABLED", "").lower() == "true") and False

    def iniciar_creacion(self, spec: EspecificacionWeb) -> dict:
        # Arquitectura preparada: cuando exista la integración, aquí se iniciaría el onboarding de Hostinger
        # y se devolvería la URL/estado. Sin integración → respuesta PREPARADA (no simula un sitio real).
        logger.debug("Hostinger.iniciar_creacion PREPARADO (sin integración) emp=%s", spec.id_empresa)
        return {"ok": False, "estado": "PREPARADO",
                "mensaje": "Integración con Hostinger pendiente de implementar (Fase posterior).",
                "spec": spec.to_dict()}

    def estado_sitio(self, referencia) -> dict:
        return {"estado": "PREPARADO", "referencia": referencia}


PROVEEDOR_OFICIAL = "hostinger"
