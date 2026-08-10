"""
Motor · SISTEMA DE VERSIONES (Fase WEB-13). Metadatos de versión de API/conector y rango soportado. Sin
lógica de conexión; el comparador es una utilidad de compatibilidad (semver simplificado).
"""

from dataclasses import dataclass


def _tupla(v: str):
    try:
        return tuple(int(x) for x in str(v).split(".") if x != "")
    except Exception:
        return (0,)


@dataclass(frozen=True)
class VersionInfo:
    api_version: str = "1.0"
    connector_version: str = "0.1.0"
    minimum_version: str = "1.0"
    maximum_version: str | None = None

    def compatible(self, version: str) -> bool:
        """¿`version` cae dentro de [minimum_version, maximum_version]? Utilidad, no realiza I/O."""
        v = _tupla(version)
        if v < _tupla(self.minimum_version):
            return False
        if self.maximum_version and v > _tupla(self.maximum_version):
            return False
        return True

    def as_dict(self) -> dict:
        return {"api_version": self.api_version, "connector_version": self.connector_version,
                "minimum_version": self.minimum_version, "maximum_version": self.maximum_version}
