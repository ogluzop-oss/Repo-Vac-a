"""
ScreenContext de SOMA (Fase 1 — núcleo). Gestor de contexto que conoce en todo momento: usuario,
empresa, tienda, almacén, módulo activo, pantalla activa, permisos e idioma. Reutiliza la resolución
de contexto del Copiloto (`copilot.contexto`) y el estado de la app; se mantiene actualizado leyendo
en vivo y aceptando notificaciones del Event Registry (pantalla activa).

Solo LECTURA de estado ya existente: no duplica sesión, tenant ni permisos.
"""

import logging

logger = logging.getLogger("soma.contexto")


class ScreenContext:
    def __init__(self):
        self._app = None
        self._modulo_activo = None      # v_id del módulo abierto (si se conoce)
        self._pantalla_activa = None    # nombre de clase de la pantalla activa

    def enlazar_app(self, app) -> None:
        """Asocia la instancia de SmartManagerApp (raíz) para leer módulo/pantalla en vivo."""
        self._app = app

    # ── Notificación desde el Event Registry (pantalla abierta) ──
    def notificar_pantalla(self, nombre_pantalla, *, modulo=None) -> None:
        self._pantalla_activa = nombre_pantalla
        if modulo:
            self._modulo_activo = modulo

    # ── Lectura en vivo del ERP ──
    def _leer_pantalla_actual(self):
        try:
            if self._app is not None and hasattr(self._app, "currentWidget"):
                w = self._app.currentWidget()
                if w is not None:
                    return type(w).__name__
        except Exception as e:
            logger.debug("leer pantalla: %s", e)
        return self._pantalla_activa

    def _base(self):
        """Contexto empresa/tienda/usuario/rol/idioma vía el resolvedor del Copiloto (reutilizado)."""
        try:
            from src.services.copilot import contexto as _c
            return _c.resolver(None, None)
        except Exception as e:
            logger.debug("contexto base: %s", e)
            return {"id_empresa": None, "id_tienda": None, "usuario": None,
                    "rol": None, "idioma": "es", "periodo": "dia"}

    def _almacen(self):
        try:
            from src.db.conexion import almacen_actual_id
            return almacen_actual_id()
        except Exception:
            return None

    def _permisos(self, usuario):
        """Permisos efectivos (best-effort) vía RBAC existente; vacío si no aplica."""
        try:
            from src.services import autorizacion
            if hasattr(autorizacion, "permisos_de"):
                return list(autorizacion.permisos_de(usuario) or [])
        except Exception as e:
            logger.debug("permisos: %s", e)
        return []

    def snapshot(self) -> dict:
        """Foto completa del contexto actual (siempre en vivo)."""
        b = self._base()
        return {
            "usuario": b.get("usuario"),
            "rol": b.get("rol"),
            "empresa": b.get("id_empresa"),
            "tienda": b.get("id_tienda"),
            "almacen": self._almacen(),
            "modulo_activo": self._modulo_activo,
            "pantalla_activa": self._leer_pantalla_actual(),
            "permisos": self._permisos({"perfil": b.get("rol")}),
            "idioma": b.get("idioma", "es"),
        }
