"""
Modelo de la Corporate Communication Platform (CCP).

`Comunicacion` es la unidad de trabajo de la plataforma: describe QUÉ se comunica, a QUIÉN y por qué
canal, con un **Communication ID** (`COM-AAAA-NNNNNNNN`) independiente del canal que unifica toda la
auditoría. `Resultado` es la respuesta de un canal. Núcleo agnóstico de framework (sin PyQt, sin
importar módulos de datos: la CCP resuelve identidades solo por el Corporate Identity Resolver).
"""

from dataclasses import dataclass, field

# Estados unificados de una comunicación (válidos para cualquier canal).
ESTADO_PREPARADA = "preparada"
ESTADO_ENVIADO = "enviado"
ESTADO_ENTREGADO = "entregado"
ESTADO_FALLIDO = "fallido"
ESTADO_NO_OPERATIVO = "no_operativo"   # canal preparado pero sin funcionalidad real

# Canales (claves estables). Solo 'email' es operativo en esta fase.
CANAL_EMAIL = "email"
CANAL_WHATSAPP = "whatsapp"
CANAL_SMS = "sms"
CANAL_PUSH = "push"
CANAL_TEAMS = "teams"
CANAL_SLACK = "slack"
CANAL_TELEGRAM = "telegram"
CANAL_FIRMA = "firma"


@dataclass
class Comunicacion:
    """Solicitud de comunicación corporativa (agnóstica de canal)."""
    id_empresa: str | None = None
    com_id: str | None = None                 # COM-AAAA-NNNNNNNN (lo asigna el servicio)
    canal: str | None = None                  # lo decide la Channel Policy si no se fuerza
    destinatarios: list = field(default_factory=list)   # List[Destinatario] o correos
    asunto: str = ""
    cuerpo: str = ""
    plantilla: str | None = None              # código de plantilla corporativa (opcional)
    variables: dict = field(default_factory=dict)       # variables de plantilla
    idioma: str | None = None
    prioridad: str = "normal"
    adjuntos: list = field(default_factory=list)
    contexto: str | None = None               # módulo desde el que se comunica
    usuario: str | None = None
    metadatos: dict = field(default_factory=dict)

    def destinatario_principal(self) -> str:
        """Dirección del primer destinatario (cadena), sea Destinatario o str."""
        if not self.destinatarios:
            return ""
        d = self.destinatarios[0]
        return getattr(d, "correo", None) or (d if isinstance(d, str) else "")


@dataclass
class Resultado:
    """Respuesta de un canal a un intento de envío."""
    ok: bool
    canal: str
    com_id: str | None = None
    estado: str = ESTADO_PREPARADA
    mensaje: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "canal": self.canal, "com_id": self.com_id,
                "estado": self.estado, "mensaje": self.mensaje}
