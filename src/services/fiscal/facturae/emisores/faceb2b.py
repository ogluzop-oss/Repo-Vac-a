"""
Canal FACeB2B (C3.4.5) — PREPARACIÓN/compatibilidad, no operativa completa.

Deja el punto de extensión listo para la factura electrónica B2B (Ley 18/2022
"Crea y Crece") sobre la misma arquitectura (Facturae + XAdES + mTLS). La operativa
real (WSDL/flujo FACeB2B, gestión de estados específicos) es trabajo futuro: por eso
`disponible()` es False y no se envía nada. ⚠️ Pendiente de especificación oficial.
"""

import logging

from src.services.fiscal.facturae.canal_base import CanalFacturae

logger = logging.getLogger("fiscal.facturae.faceb2b")

# Endpoints FACeB2B (placeholder). ⚠️[verificar WSDL/URLs oficiales]
_ENDPOINT = {
    "preproduccion": "https://se-facturae-webservice.redsara.es/facturab2b/ws",
    "produccion": "https://facturae.gob.es/facturab2b/ws",
}


class CanalFACeB2B(CanalFacturae):
    nombre = "faceb2b"

    def __init__(self, transporte=None, config=None):
        self._transporte = transporte
        self.config = config or {}

    def disponible(self) -> bool:
        # Preparado pero NO operativo en C3.4 (la operativa B2B real es épica futura).
        return False

    def endpoint(self, config: dict) -> str:
        ent = (config or {}).get("entorno", "preproduccion")
        return _ENDPOINT.get(ent, _ENDPOINT["preproduccion"])

    def enviar(self, xml_firmado: bytes, datos: dict, config: dict) -> dict:
        return {"ok": False, "estado": "pendiente",
                "mensaje": "FACeB2B preparado pero no operativo (épica futura)"}
