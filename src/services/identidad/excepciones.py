"""
IOC v2 · Identity API — excepciones propias (Bloque 2.1).

La Identity API nunca lanza excepciones genéricas: usa esta jerarquía tipada para que los
consumidores puedan distinguir el tipo de fallo. Todas derivan de `IdentityException` y llevan un
`codigo` estable y un `detalle` estructurado (serializable a `IdentityError`).
"""


class IdentityException(Exception):
    """Base de todas las excepciones de la Identity API."""
    codigo = "IDENTITY_ERROR"

    def __init__(self, mensaje="", *, detalle=None, entidad=None, id_empresa=None):
        super().__init__(mensaje or self.codigo)
        self.mensaje = mensaje or self.codigo
        self.detalle = detalle or {}
        self.entidad = entidad
        self.id_empresa = id_empresa

    def to_error(self):
        """Convierte la excepción en el modelo público `IdentityError`."""
        from src.services.identidad.modelos import IdentityError
        return IdentityError(codigo=self.codigo, mensaje=self.mensaje, entidad=self.entidad,
                             id_empresa=self.id_empresa, detalle=self.detalle)


class IdentityNotFound(IdentityException):
    codigo = "IDENTITY_NOT_FOUND"


class IdentityConflict(IdentityException):
    codigo = "IDENTITY_CONFLICT"


class IdentityValidationError(IdentityException):
    codigo = "IDENTITY_VALIDATION_ERROR"


class IdentityPermissionError(IdentityException):
    codigo = "IDENTITY_PERMISSION_ERROR"


class IdentityHierarchyError(IdentityException):
    codigo = "IDENTITY_HIERARCHY_ERROR"


class IdentityStateError(IdentityException):
    codigo = "IDENTITY_STATE_ERROR"
