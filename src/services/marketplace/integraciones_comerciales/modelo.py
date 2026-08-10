"""
Integraciones Comerciales · Modelo de CONFIGURACIÓN (Fase WEB-03). Metadatos de una integración con una
plataforma ecommerce. **NUNCA almacena credenciales reales**: sólo una REFERENCIA (`credenciales_ref`, p. ej.
el nombre del secreto en Secret Manager). El valor del secreto vive en Secret Manager, no aquí.
"""

import time

from src.services.marketplace.integraciones_comerciales import estados as E


class Integracion:
    """Configuración de una integración (sin secretos). `credenciales_ref` = puntero a Secret Manager."""
    __slots__ = ("id_empresa", "plataforma", "nombre", "tipo", "estado", "url", "version",
                 "ultima_sync", "frecuencia", "observaciones", "credenciales_ref", "habilitada", "creado")

    def __init__(self, id_empresa, plataforma, *, nombre=None, tipo=None, url=None, version=None,
                 frecuencia=None, observaciones=None, credenciales_ref=None, estado=None):
        self.id_empresa = str(id_empresa)
        self.plataforma = plataforma
        self.nombre = nombre or plataforma
        self.tipo = tipo                      # 'ecommerce' | 'marketplace'
        self.url = url
        self.version = version
        self.frecuencia = frecuencia          # p. ej. 'manual' | 'horaria' | 'diaria'
        self.observaciones = observaciones
        self.credenciales_ref = credenciales_ref   # NOMBRE del secreto, nunca el valor
        self.habilitada = True
        self.estado = estado or (E.CONFIGURADA if credenciales_ref else E.NO_CONFIGURADA)
        self.ultima_sync = None
        self.creado = time.time()

    def to_dict(self) -> dict:
        # Expone `credenciales_ref` (un nombre), NUNCA un secreto.
        return {k: getattr(self, k) for k in self.__slots__}
