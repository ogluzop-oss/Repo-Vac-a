"""
Canal Web · Proveedores de creación de web (Fase WEB-02) — CONTRATO abstracto. Un `ProveedorWeb` crea una
página web profesional desde cero para una empresa. Es una ABSTRACCIÓN provider-agnostic: hoy sólo se define
la interfaz; las implementaciones reales (API/OAuth/sync) se añaden después. Ningún proveedor real se ejecuta.
"""


class EspecificacionWeb:
    """Datos mínimos para solicitar la creación de una web (sin secretos)."""
    __slots__ = ("id_empresa", "nombre", "dominio_deseado", "idioma", "moneda", "color", "logo_url")

    def __init__(self, id_empresa, *, nombre=None, dominio_deseado=None, idioma="es",
                 moneda="EUR", color=None, logo_url=None):
        self.id_empresa = id_empresa
        self.nombre = nombre
        self.dominio_deseado = dominio_deseado
        self.idioma = idioma
        self.moneda = moneda
        self.color = color
        self.logo_url = logo_url

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}


class ProveedorWeb:
    """Interfaz de un proveedor de creación de web. Las implementaciones NO deben guardar secretos en claro
    (usar Secret Manager) y deben ser DEGRADABLES: si no hay credenciales/servicio, `disponible()` = False."""

    clave = "base"
    nombre = "Proveedor base"
    oficial = False

    def disponible(self) -> bool:
        """True sólo si el proveedor puede operar realmente (credenciales/servicio). Base → False."""
        return False

    def iniciar_creacion(self, spec: "EspecificacionWeb") -> dict:
        """Inicia el asistente de creación (devuelve p. ej. una URL de onboarding). PREPARADO."""
        raise NotImplementedError

    def estado_sitio(self, referencia) -> dict:
        """Estado del sitio en creación/creado. PREPARADO."""
        raise NotImplementedError

    def descriptor(self) -> dict:
        return {"clave": self.clave, "nombre": self.nombre, "oficial": self.oficial,
                "disponible": self.disponible()}
