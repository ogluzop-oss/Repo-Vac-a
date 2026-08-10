"""
Actualizador empresarial (Fase 4, SUBFASE 4.8/4.9).

Framework de actualizacion: manifiesto de versiones (canal normal/emergencia), verificacion de
integridad (hash + firma), ventana de mantenimiento (03:00, fuera de horario laboral) y canal
de EMERGENCIA para parches criticos (error fiscal/Verifactu/seguridad) que NO esperan a las 3:00.

NOTA: la descarga/instalacion/reinicio del binario es especifica de plataforma y potencialmente
destructiva; esta fase entrega el MECANISMO (comprobacion, verificacion, ventana, estado y canal
de emergencia). El paso final de instalar/reiniciar se conecta aqui sin rediseñar el resto.
"""

from src.services.actualizador.updater import (aplicar,                # noqa: F401
                                               canal_emergencia,
                                               disponibles, en_ventana,
                                               publicar,
                                               verificar_integridad)

__all__ = ["publicar", "disponibles", "canal_emergencia", "verificar_integridad",
           "en_ventana", "aplicar"]
