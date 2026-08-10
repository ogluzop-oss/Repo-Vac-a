"""
Portal · Sesión (Fase V · Bloque 2). Sesión del portal web: tipo de portal + tenant + scopes,
sobre el JWT oficial (reutiliza `src.seguridad.tokens`). El tenant sale SIEMPRE del token. Sin BD.
"""

from __future__ import annotations

from src.services.portal import acceso, portales


class SesionPortal:
    def __init__(self, tipo_portal, token=None):
        self.tipo = tipo_portal if tipo_portal in portales.TIPOS else "cliente"
        self.token = token
        self._claims = None

    def claims(self):
        if self.token and self._claims is None:
            try:
                from src.seguridad import tokens
                self._claims = tokens.verificar(self.token, "access")
            except Exception:
                self._claims = None
        return self._claims or {}

    def id_empresa(self):
        return self.claims().get("empresa")

    def id_usuario(self):
        return self.claims().get("sub")

    def valida(self):
        return bool(self.claims())

    def scopes(self):
        return portales.scopes(self.tipo)

    def puede(self, funcionalidad):
        return acceso.puede(self.tipo, funcionalidad)

    def menu(self):
        """Funcionalidades visibles para este portal (respetando scopes)."""
        return portales.funcionalidades(self.tipo)


__all__ = ["SesionPortal"]
