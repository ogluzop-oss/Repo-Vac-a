"""
Contrato de canal de la CCP. Cada canal (Email operativo; WhatsApp/SMS/… preparados) implementa esta
interfaz. El Corporate Communication Service delega el envío en el canal; nunca envía directamente.
"""

from src.services.ccp.modelo import Resultado, ESTADO_NO_OPERATIVO


class CanalComunicacion:
    """Interfaz base de un canal de comunicación."""
    clave = ""
    nombre = ""
    operativo = False   # solo Email es True en esta fase

    def disponible(self) -> bool:
        return bool(self.operativo)

    def enviar(self, comunicacion) -> Resultado:
        raise NotImplementedError


class CanalPreparado(CanalComunicacion):
    """Canal PREPARADO arquitectónicamente pero SIN funcionalidad real (no envía)."""
    operativo = False

    def enviar(self, comunicacion) -> Resultado:
        return Resultado(ok=False, canal=self.clave, com_id=getattr(comunicacion, "com_id", None),
                         estado=ESTADO_NO_OPERATIVO,
                         mensaje=f"Canal '{self.clave}' preparado; sin envío real en esta fase.")
