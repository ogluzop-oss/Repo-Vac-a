"""
Mobile · Sesión (Fase V · Bloque 1). Estado de sesión del dispositivo: tokens vigentes, usuario/
tenant y caducidad. Se apoya en `auth` (que reutiliza la seguridad oficial). Sin BD.
"""

from __future__ import annotations

import time


class SesionMovil:
    def __init__(self, access=None, refresh=None):
        self.access = access
        self.refresh = refresh
        self._claims = None
        self._creada = time.time()

    def claims(self):
        if self.access and self._claims is None:
            from src.services.mobile import auth
            self._claims = auth.verificar(self.access, "access")
        return self._claims or {}

    def id_empresa(self):
        return self.claims().get("empresa")

    def id_usuario(self):
        return self.claims().get("sub")

    def valida(self):
        return bool(self.claims())

    def refrescar(self):
        """Renueva el access token usando el refresh (rotación de sesión)."""
        from src.services.mobile import auth
        nuevos = auth.refrescar(self.refresh) if self.refresh else None
        if nuevos:
            self.access = nuevos["access"]; self.refresh = nuevos["refresh"]
            self._claims = None
            return True
        return False

    def cerrar(self):
        self.access = self.refresh = self._claims = None


__all__ = ["SesionMovil"]
