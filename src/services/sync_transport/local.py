"""
Transporte LOCAL / loopback (Fase 4, SUBFASE 4.1). Implementacion de referencia del contrato
`Transporte`: entrega el paquete a la terminal destino y confirma la recepcion. En un despliegue
de un solo nodo (BD compartida) la "entrega" marca el paquete como RECIBIDO; el motor lo aplica
a continuacion. Los transportes de red (LAN/VPN/Internet/Cloud) implementaran el mismo contrato
sin que el resto de la plataforma cambie.
"""

import logging

from src.services.sync_transport.base import ResultadoTransporte, Transporte

logger = logging.getLogger("sync_transport.local")


class LocalLoopback(Transporte):
    nombre = "local"

    def disponible(self, destino_tienda, id_empresa=None) -> bool:
        try:
            from src.services.distribucion import terminales
            return terminales.esta_online(destino_tienda, id_empresa)
        except Exception:
            return True

    def enviar(self, paquete: dict, destino_tienda, id_empresa=None) -> ResultadoTransporte:
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("UPDATE sync_paquetes SET estado='RECIBIDO' WHERE id=%s", (paquete.get("id"),))
                c.commit()
            return ResultadoTransporte(True, bytes=int(paquete.get("bytes_comprimido") or 0),
                                       detalle="entregado (loopback)")
        except Exception as e:
            logger.error("enviar local: %s", e)
            return ResultadoTransporte(False, detalle=str(e))
