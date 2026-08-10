"""
Versionado semántico (Fase IV · Bloque 3). Cada servicio declara Major.Minor.Patch y su
compatibilidad. Regla SemVer: compatibles si comparten Major (y el disponible ≥ requerido).
Sin dependencias externas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RE = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True, order=True)
class Version:
    major: int = 1
    minor: int = 0
    patch: int = 0

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def parse(cls, texto) -> "Version":
        if isinstance(texto, Version):
            return texto
        m = _RE.match(str(texto or ""))
        if not m:
            return cls(0, 0, 0)
        return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    def compatible_con(self, requerido) -> bool:
        """Compatible si comparten Major y self (disponible) >= requerido."""
        req = Version.parse(requerido)
        return self.major == req.major and self >= req

    def en_rango(self, minimo=None, maximo=None) -> bool:
        if minimo and self < Version.parse(minimo):
            return False
        if maximo and self > Version.parse(maximo):
            return False
        return True


def comparar(a, b) -> int:
    """-1, 0, 1 según a<b, a==b, a>b."""
    va, vb = Version.parse(a), Version.parse(b)
    return (va > vb) - (va < vb)


__all__ = ["Version", "comparar"]
