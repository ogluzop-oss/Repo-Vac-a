"""
Transporte fisico, replicacion diferencial y operacion distribuida (Fase 4).

Convierte la distribucion LOGICA (Fase 2) en sincronizacion REAL entre terminales:
transporte desacoplado (local/LAN/VPN/Internet/Cloud), paquetes diferenciales comprimidos,
aplicacion idempotente con reanudacion, ACK real, control de versiones, descubrimiento,
consistencia y observabilidad. Reutiliza la infra de Fases 1-3; no la rediseña.

Uso tipico (backend):
    from src.services import sync_transport as ST
    ST.descubrir()                 # alta automatica de terminales
    ST.sincronizar(destino_tienda=1)
    ST.reanudar()                  # continua paquetes incompletos
"""

from src.services.sync_transport import (base, consistencia,           # noqa: F401
                                         descubrimiento, motor,
                                         paquetes, registry, versiones)
from src.services.sync_transport.consistencia import (solicitar_resync,  # noqa: F401
                                                      verificar)
from src.services.sync_transport.descubrimiento import descubrir       # noqa: F401
from src.services.sync_transport.motor import (reanudar, sincronizar,  # noqa: F401
                                               sincronizar_todas)

__all__ = [
    "sincronizar", "sincronizar_todas", "reanudar", "descubrir", "verificar",
    "solicitar_resync", "base", "registry", "paquetes", "motor", "versiones",
    "descubrimiento", "consistencia",
]
