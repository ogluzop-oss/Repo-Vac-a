"""
Motor de replicacion (Fase 4, SUBFASE 4.2). Replica CAMBIOS (no tablas): cada cambio recibido
en un paquete se aplica en la terminal destino de forma idempotente y consciente de la version
(entidad_versiones, Fase 2). Extensible por entidad: cada dominio (articulos/precios/clientes/
stock/pedidos/usuarios/permisos/documentos/RRHH/CRM/contabilidad/tesoreria...) puede registrar
su aplicador concreto sin tocar el motor.

En un despliegue de un solo nodo (BD compartida) el aplicador por defecto NO reescribe la tabla
de negocio (ya existe el dato): registra la version replicada. En un nodo remoto real, el
aplicador concreto haria el upsert del payload sobre su copia local.
"""

from src.services.replicacion.aplicador import (aplicar,               # noqa: F401
                                                aplicadores_registrados,
                                                registrar_aplicador)

__all__ = ["aplicar", "registrar_aplicador", "aplicadores_registrados"]
