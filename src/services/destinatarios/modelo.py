"""
Modelo del Servicio Corporativo de Resolución de Destinatarios.

`Destinatario` es el objeto ENRIQUECIDO que devuelve SIEMPRE el servicio (nunca una cadena suelta):
lleva identidad, tipo, estado, empresa, avisos, prioridad/score y origen, de modo que cualquier canal
(Correo, WhatsApp, SMS, push, IA, Bots, Firma…) pueda consumirlo. La conversión a texto plano (p. ej.
la propia dirección de correo) es responsabilidad del consumidor, no del servicio.

Núcleo AGNÓSTICO de framework: sin PyQt, sin dependencia del módulo Correo.
"""

from dataclasses import dataclass, field

# Tipos de destinatario (origen conceptual). Ampliable sin tocar el núcleo: cada adaptador declara
# el suyo. La etiqueta VISUAL asociada vive en ETIQUETAS (para Correo/otros canales).
TIPO_CLIENTE = "cliente"
TIPO_PROVEEDOR = "proveedor"
TIPO_EMPLEADO = "empleado"
TIPO_USUARIO = "usuario"
TIPO_TRANSPORTISTA = "transportista"
TIPO_BANCO = "banco"
TIPO_CONTACTO = "contacto"
TIPO_CENTRO = "centro"
TIPO_TIENDA = "tienda"
TIPO_ALMACEN = "almacen"
TIPO_REPRESENTANTE = "representante"
TIPO_ACREEDOR = "acreedor"
TIPO_LEAD = "lead"
TIPO_HISTORICO = "historico"

ETIQUETAS = {
    TIPO_CLIENTE: "Cliente",
    TIPO_PROVEEDOR: "Proveedor",
    TIPO_EMPLEADO: "Empleado",
    TIPO_USUARIO: "Usuario",
    TIPO_TRANSPORTISTA: "Transportista",
    TIPO_BANCO: "Banco",
    TIPO_CONTACTO: "Contacto",
    TIPO_CENTRO: "Centro de trabajo",
    TIPO_TIENDA: "Tienda",
    TIPO_ALMACEN: "Almacén",
    TIPO_REPRESENTANTE: "Representante",
    TIPO_ACREEDOR: "Acreedor",
    TIPO_LEAD: "Lead / Candidato",
    TIPO_HISTORICO: "Reciente",
}

# Estados que generan aviso visual (Parte M). No impiden el envío: solo advierten.
ESTADOS_AVISO = {
    "inactivo": "Empleado/registro inactivo",
    "baja": "Dado de baja",
    "bloqueado": "Proveedor bloqueado",
    "archivado": "Registro archivado",
    "deshabilitado": "Usuario deshabilitado",
    "suspendido": "Registro suspendido",
    "inhabilitado": "Registro inhabilitado",
}


def etiqueta_de(tipo: str) -> str:
    return ETIQUETAS.get(tipo, (tipo or "Contacto").capitalize())


@dataclass
class Destinatario:
    """Destinatario corporativo enriquecido. Identidad + metadatos para cualquier canal."""
    correo: str
    nombre_mostrado: str = ""
    tipo: str = TIPO_CONTACTO
    id_empresa: str | None = None
    modulo_origen: str | None = None          # adaptador/módulo del que procede
    id_origen: str | int | None = None        # id del registro en su módulo original
    estado: str | None = None                 # activo/inactivo/bloqueado/archivado…
    avisos: list = field(default_factory=list)     # advertencias (Parte M)
    score: float = 0.0                         # prioridad de ordenación (Parte G)
    favorito: bool = False                     # (Parte I)
    reciente: bool = False                     # aparece en histórico (Parte J)
    num_envios: int = 0                        # frecuencia (Parte Q)
    # Campos auxiliares para búsqueda/desambiguación (Partes E/F/L): razon_social, cif, telefono,
    # alias, empresa_nombre… No se persisten; solo enriquecen la sugerencia.
    extra: dict = field(default_factory=dict)
    # Perfil ampliado (CCP Parte F) — PREPARADO: campos opcionales para comunicaciones multicanal.
    # No es obligatorio rellenarlos ahora; la estructura queda lista para el futuro.
    departamento: str | None = None
    cargo: str | None = None
    idioma: str | None = None
    canal_preferido: str | None = None
    correo_preferido: str | None = None
    rgpd: bool | None = None
    ultimo_contacto: str | None = None
    num_comunicaciones: int = 0
    fecha_ultimo_envio: str | None = None
    foto: str | None = None
    tipo_entidad: str | None = None

    def __post_init__(self):
        self.correo = (self.correo or "").strip()
        self.nombre_mostrado = (self.nombre_mostrado or "").strip()
        # Aviso automático por estado (no bloquea; Parte M).
        est = (self.estado or "").strip().lower()
        if est in ESTADOS_AVISO and ESTADOS_AVISO[est] not in self.avisos:
            self.avisos.append(ESTADOS_AVISO[est])

    @property
    def etiqueta(self) -> str:
        """Etiqueta visual del tipo (Parte K)."""
        return etiqueta_de(self.tipo)

    @property
    def clave(self) -> str:
        """Clave de deduplicación: correo normalizado (Parte P/L)."""
        return self.correo.strip().lower()

    def tiene_avisos(self) -> bool:
        return bool(self.avisos)

    def to_dict(self) -> dict:
        return {
            "correo": self.correo,
            "nombre_mostrado": self.nombre_mostrado,
            "tipo": self.tipo,
            "etiqueta": self.etiqueta,
            "id_empresa": self.id_empresa,
            "modulo_origen": self.modulo_origen,
            "id_origen": self.id_origen,
            "estado": self.estado,
            "avisos": list(self.avisos),
            "score": round(self.score, 4),
            "favorito": self.favorito,
            "reciente": self.reciente,
            "num_envios": self.num_envios,
            "extra": dict(self.extra),
            # Perfil ampliado (CCP Parte F).
            "departamento": self.departamento, "cargo": self.cargo, "idioma": self.idioma,
            "canal_preferido": self.canal_preferido, "correo_preferido": self.correo_preferido,
            "rgpd": self.rgpd, "ultimo_contacto": self.ultimo_contacto,
            "num_comunicaciones": self.num_comunicaciones,
            "fecha_ultimo_envio": self.fecha_ultimo_envio, "foto": self.foto,
            "tipo_entidad": self.tipo_entidad,
        }
