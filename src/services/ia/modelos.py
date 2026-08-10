"""
Estructuras de datos de la capa de IA (solo lectura). Son objetos ligeros de PRESENTACION de
resultados analiticos; no persisten nada nuevo (la IA nunca duplica ni almacena datos del ERP).
"""

from dataclasses import dataclass, field


@dataclass
class Insight:
    tipo: str
    titulo: str
    detalle: str = ""
    severidad: str = "info"          # info | ok | aviso | critico
    datos: dict = field(default_factory=dict)

    def to_dict(self):
        return {"tipo": self.tipo, "titulo": self.titulo, "detalle": self.detalle,
                "severidad": self.severidad, "datos": self.datos}


@dataclass
class Recomendacion:
    accion: str
    motivo: str
    entidad: str = ""
    entidad_id: str = ""
    prioridad: str = "MEDIA"
    workflow: str = ""               # circuito Workflow/BPM sugerido (la ejecucion es humana)
    datos: dict = field(default_factory=dict)

    def to_dict(self):
        return {"accion": self.accion, "motivo": self.motivo, "entidad": self.entidad,
                "entidad_id": self.entidad_id, "prioridad": self.prioridad,
                "workflow": self.workflow, "datos": self.datos}


@dataclass
class Anomalia:
    tipo: str
    descripcion: str
    severidad: str = "media"         # baja | media | alta
    valor: object = None
    esperado: object = None
    datos: dict = field(default_factory=dict)

    def to_dict(self):
        return {"tipo": self.tipo, "descripcion": self.descripcion, "severidad": self.severidad,
                "valor": self.valor, "esperado": self.esperado, "datos": self.datos}


@dataclass
class Prediccion:
    metrica: str
    horizonte: str
    valor: object
    confianza: float = 0.5
    detalle: str = ""

    def to_dict(self):
        return {"metrica": self.metrica, "horizonte": self.horizonte, "valor": self.valor,
                "confianza": round(self.confianza, 2), "detalle": self.detalle}


@dataclass
class Riesgo:
    tipo: str
    nivel: str                       # bajo | medio | alto
    score: float
    descripcion: str = ""
    entidad: str = ""
    entidad_id: str = ""

    def to_dict(self):
        return {"tipo": self.tipo, "nivel": self.nivel, "score": round(self.score, 2),
                "descripcion": self.descripcion, "entidad": self.entidad, "entidad_id": self.entidad_id}


@dataclass
class RespuestaIA:
    intent: str
    texto: str
    datos: object = None
    recomendaciones: list = field(default_factory=list)

    def to_dict(self):
        return {"intent": self.intent, "texto": self.texto, "datos": self.datos,
                "recomendaciones": [r.to_dict() if hasattr(r, "to_dict") else r
                                    for r in self.recomendaciones]}
