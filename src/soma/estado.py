"""
Máquina de estados de SOMA (Fase 1 — núcleo). LÓGICA pura, sin Qt ni animaciones: define los
estados del asistente y las transiciones válidas, y notifica a observadores (personaje/espacio/
indicador se conectarán en fases posteriores). Framework-agnóstica y testeable.
"""

import logging

logger = logging.getLogger("soma.estado")

# ── Estados (los 9 exigidos) ──────────────────────────────────────────────────
DORMIDO = "DORMIDO"
APARECIENDO = "APARECIENDO"
ESCUCHANDO = "ESCUCHANDO"
PENSANDO = "PENSANDO"
PROCESANDO = "PROCESANDO"
HABLANDO = "HABLANDO"
ESPERANDO = "ESPERANDO"
CONFIRMACION = "CONFIRMACION"
ERROR = "ERROR"
DESAPARECIENDO = "DESAPARECIENDO"

ESTADOS = (DORMIDO, APARECIENDO, ESCUCHANDO, PENSANDO, PROCESANDO, HABLANDO, ESPERANDO,
           CONFIRMACION, ERROR, DESAPARECIENDO)

# Transiciones válidas por estado. Además, SIEMPRE se permiten ERROR, DESAPARECIENDO y DORMIDO
# (salidas de seguridad / reset) desde cualquier estado.
#   ESPERANDO = "activo pero en reposo/feliz" (no se está diciendo nada).
#   ESCUCHANDO = solo mientras el trabajador está diciendo/escribiendo algo.
#   PENSANDO = silencio entre la consulta y la respuesta. PROCESANDO = entre la orden y su ejecución.
#   HABLANDO = respondiendo (explicando). CONFIRMACION = confirmación. ERROR = no puede responder/ejecutar.
_TRANSICIONES = {
    DORMIDO:        {APARECIENDO},
    APARECIENDO:    {ESCUCHANDO, ESPERANDO},
    ESCUCHANDO:     {PENSANDO, PROCESANDO, ESPERANDO},
    PENSANDO:       {HABLANDO, PROCESANDO, CONFIRMACION, ESPERANDO, ERROR},
    PROCESANDO:     {HABLANDO, CONFIRMACION, ESPERANDO, ERROR},
    HABLANDO:       {ESPERANDO, ESCUCHANDO, CONFIRMACION},
    ESPERANDO:      {ESCUCHANDO, PENSANDO, PROCESANDO, CONFIRMACION, HABLANDO},
    CONFIRMACION:   {ESPERANDO, ESCUCHANDO},
    ERROR:          {ESPERANDO, ESCUCHANDO},
    DESAPARECIENDO: {DORMIDO},
}
_SIEMPRE = {ERROR, DESAPARECIENDO, DORMIDO}


class MaquinaEstados:
    """Mantiene el estado actual y valida las transiciones. Notifica a los observadores registrados
    con `(estado_anterior, estado_nuevo)`. No conoce nada de la GUI."""

    def __init__(self, inicial=DORMIDO):
        self._estado = inicial
        self._observadores = []

    @property
    def estado(self) -> str:
        return self._estado

    def es_valida(self, destino: str) -> bool:
        if destino not in ESTADOS:
            return False
        if destino == self._estado:
            return True
        return destino in _SIEMPRE or destino in _TRANSICIONES.get(self._estado, set())

    def transicionar(self, destino: str, *, forzar: bool = False) -> bool:
        """Cambia de estado si la transición es válida (o `forzar=True`). Devuelve si cambió."""
        if destino not in ESTADOS:
            logger.debug("estado desconocido ignorado: %s", destino)
            return False
        if destino == self._estado:
            return False
        if not forzar and not self.es_valida(destino):
            logger.debug("transición inválida %s → %s (ignorada)", self._estado, destino)
            return False
        anterior, self._estado = self._estado, destino
        for cb in list(self._observadores):
            try:
                cb(anterior, destino)
            except Exception as e:
                logger.debug("observador de estado falló: %s", e)
        return True

    def suscribir(self, callback) -> None:
        """Registra un observador `callback(anterior, nuevo)` (personaje/espacio/indicador)."""
        if callback not in self._observadores:
            self._observadores.append(callback)

    def desuscribir(self, callback) -> None:
        if callback in self._observadores:
            self._observadores.remove(callback)

    def reset(self) -> None:
        self.transicionar(DORMIDO, forzar=True)
