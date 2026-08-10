"""
Memoria conversacional de SOMA (Fase 1 — núcleo). REUTILIZA la memoria del Copiloto
(`copilot.memoria`, en proceso, por usuario). Reside en el kernel → la conversación NO se pierde
durante la sesión aunque el personaje desaparezca. v1: solo sesión (no persistente en BD).

No crea un almacén paralelo: es un envoltorio fino sobre el sistema existente.
"""

import logging

logger = logging.getLogger("soma.memoria")


class MemoriaConversacional:
    def _mem(self):
        from src.services.copilot import memoria as _m
        return _m

    def recordar(self, usuario, **datos) -> None:
        try:
            self._mem().recordar(usuario, **datos)
        except Exception as e:
            logger.debug("recordar: %s", e)

    def contexto(self, usuario) -> dict:
        try:
            return self._mem().contexto(usuario) or {}
        except Exception as e:
            logger.debug("contexto memoria: %s", e)
            return {}

    def historial(self, usuario) -> list:
        return list(self.contexto(usuario).get("consultas", []))
