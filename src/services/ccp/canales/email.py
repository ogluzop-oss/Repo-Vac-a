"""
Email Channel — ÚNICO canal operativo de la CCP en esta fase.

Envuelve el motor de envío EXISTENTE (`src.services.correo.enviar_documento`) sin modificarlo: elige
un buzón corporativo activo de la empresa (preferentemente afín al contexto) y delega el envío. OAuth/
Gmail/SMTP/IMAP/plantillas/adjuntos/auditoría del correo permanecen intactos.
"""

import logging

from src.services.ccp.canales.base import CanalComunicacion
from src.services.ccp.modelo import ESTADO_ENVIADO, ESTADO_FALLIDO, Resultado

logger = logging.getLogger("ccp.canal.email")

# Sugerencia de buzón por contexto de módulo → tipo de buzón corporativo (correos_corporativos.tipo).
_CONTEXTO_A_TIPO = {
    "compras": "pedidos", "aprovisionamiento": "pedidos", "proveedores": "pedidos",
    "rrhh": "rrhh", "laboral": "rrhh", "portal_empleado": "rrhh",
    "logistica": "logistica", "almacenes": "logistica",
    "administracion": "administracion", "facturacion": "administracion",
    "incidencias": "incidencias", "sat": "incidencias",
}


class EmailChannel(CanalComunicacion):
    clave = "email"
    nombre = "Correo electrónico"
    operativo = True

    def _elegir_buzon(self, id_empresa, contexto, id_correo=None):
        from src.db import correo as correo_db
        # Si el consumidor indicó un buzón concreto (p. ej. el diálogo de Correo), se respeta.
        if id_correo:
            b = correo_db.obtener_correo(id_correo)
            if b and b.get("estado") == "activo":
                return b
        buzones = [c for c in correo_db.listar_correos(id_empresa) if c.get("estado") == "activo"]
        if not buzones:
            return None
        tipo_pref = _CONTEXTO_A_TIPO.get((contexto or "").lower())
        if tipo_pref:
            for b in buzones:
                if b.get("tipo") == tipo_pref:
                    return b
        # Si no hay afín, prioriza un buzón 'general', si no el primero activo.
        for b in buzones:
            if b.get("tipo") == "general":
                return b
        return buzones[0]

    def enviar(self, comunicacion) -> Resultado:
        com_id = getattr(comunicacion, "com_id", None)
        destinatario = comunicacion.destinatario_principal()
        if not destinatario or "@" not in destinatario:
            return Resultado(ok=False, canal=self.clave, com_id=com_id, estado=ESTADO_FALLIDO,
                             mensaje="Destinatario de correo no válido.")
        buzon = self._elegir_buzon(comunicacion.id_empresa, comunicacion.contexto,
                                   (comunicacion.metadatos or {}).get("id_correo"))
        if not buzon:
            return Resultado(ok=False, canal=self.clave, com_id=com_id, estado=ESTADO_FALLIDO,
                             mensaje="No hay buzón corporativo activo en la empresa.")
        try:
            from src.services import correo as correo_svc
            ok, msg = correo_svc.enviar_documento(
                buzon["id_correo"], destinatario, comunicacion.asunto or "",
                comunicacion.cuerpo or "", comunicacion.adjuntos or None)
        except Exception as e:
            logger.error("EmailChannel envío: %s", e)
            return Resultado(ok=False, canal=self.clave, com_id=com_id, estado=ESTADO_FALLIDO,
                             mensaje=f"Error de envío: {e}")
        return Resultado(ok=ok, canal=self.clave, com_id=com_id,
                         estado=ESTADO_ENVIADO if ok else ESTADO_FALLIDO, mensaje=msg)
