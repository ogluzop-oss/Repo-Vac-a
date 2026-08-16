"""Avisos de la Lonja a ambas partes.

- Empresa COMPRADORA = tenant → notificación real vía `notificaciones.emitir` (id_empresa).
- VENDEDOR = identidad global (no es un tenant) → se registra un evento de auditoría que su portal
  mostrará (y que el enlace remoto entregará el día del despliegue).
Best-effort: un aviso que falle nunca rompe la operación.
"""

from ._common import _audit, logger


def avisar_empresa(id_empresa, tipo, titulo, mensaje, prioridad="normal") -> None:
    if not id_empresa:
        return
    try:
        from src.services import notificaciones
        notificaciones.emitir(tipo, titulo, mensaje, prioridad=prioridad, modulo="lonja",
                              roles=["ADMINISTRADOR", "GERENTE"], id_empresa=id_empresa)
    except Exception as e:
        logger.debug("avisar_empresa: %s", e)


def avisar_vendedor(id_vendedor, evento, detalle="") -> None:
    _audit(evento, f"vendedor={id_vendedor}:{detalle}", "lonja_vendedores")
