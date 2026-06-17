"""
Contrato de canal de entrega de Facturae (C3.4.4) — multicanal.

`CanalFacturae` abstrae el destino (FACe B2G, FACeB2B, otros) para que el servicio
no dependa del canal. Mismo patrón que `Emisor` (C3.3). Transporte inyectable para
tests sin red; `disponible()=False` sin transporte/certificado.
"""


class CanalFacturae:
    nombre = "base"

    def disponible(self) -> bool:
        return False

    def enviar(self, xml_firmado: bytes, datos: dict, config: dict) -> dict:
        """Entrega la factura. Devuelve {ok, estado, numero_registro, csv, mensaje}."""
        return {"ok": False, "estado": "pendiente", "mensaje": "canal no configurado"}

    def consultar(self, numero_registro: str, config: dict) -> dict:
        """Consulta el estado de una factura ya entregada."""
        return {"ok": False, "mensaje": "no soportado"}
