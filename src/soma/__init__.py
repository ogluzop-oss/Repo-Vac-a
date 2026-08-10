"""
SOMA — Copiloto IA de Smart Manager AI (subsistema propio, independiente del plan UI Enterprise).

Fase 1: núcleo arquitectónico. Un ÚNICO `SomaKernel` residente durante toda la sesión, que reutiliza
la infraestructura existente (SomaWorker/SomaTTS, CopilotService, AgentManager=Especialistas IA,
Event Bus/Registry, Scheduler). Separación estricta lógica (`src/soma/`) / GUI (`src/gui/soma/`, en
fases posteriores).

Punto de entrada ÚNICO (singleton):
    from src.soma import kernel
    kernel().iniciar(app)      # tras el login
    kernel().estado            # estado actual
    kernel().shutdown()        # al cerrar la app
"""

from src.soma.kernel import SomaKernel  # noqa: F401

_kernel = None


def kernel() -> SomaKernel:
    """Devuelve el SomaKernel residente (singleton). Nunca se crea más de una vez por proceso."""
    global _kernel
    if _kernel is None:
        _kernel = SomaKernel()
    return _kernel


__all__ = ["kernel", "SomaKernel"]
