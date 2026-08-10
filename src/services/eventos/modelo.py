"""
Modelo estandar de evento (Fase 1). Nunca depender unicamente del payload: la cabecera
lleva contexto (empresa/tienda/almacen/usuario/origen/destino), control (prioridad/estado/
version) e integridad (hash). El payload es informacion adicional del dominio.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from src.services.eventos import estados as E
from src.services.eventos import prioridades as P

SCHEMA_VERSION = 1
CREATED_WITH = "smart-eventos-1.0"


def _uuid() -> str:
    return str(uuid4())


@dataclass
class Evento:
    tipo: str
    id_empresa: str
    id_tienda: int = 0
    id_almacen: int | None = None
    usuario: str | None = None
    origen: str | None = None
    destino: str | None = None
    prioridad: str = P.MEDIA
    estado: str = E.CREADO
    version: int = 1
    schema_version: int = SCHEMA_VERSION
    created_with: str = CREATED_WITH
    updated_with: str | None = None
    ref_entidad: str | None = None
    ref_id: str | None = None
    payload: dict | None = None
    observaciones: str | None = None
    uuid: str = field(default_factory=_uuid)
    id: int | None = None
    hash: str | None = None
    fecha_creacion: datetime | None = None

    def __post_init__(self):
        self.prioridad = P.normalizar(self.prioridad)
        self.estado = E.normalizar(self.estado)
        if not self.hash:
            self.hash = self.calcular_hash()

    def payload_json(self) -> str | None:
        if self.payload is None:
            return None
        try:
            return json.dumps(self.payload, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return json.dumps(str(self.payload), ensure_ascii=False)

    def calcular_hash(self) -> str:
        """Huella de integridad del evento (independiente del id autoincremental)."""
        base = "|".join([
            self.uuid, str(self.tipo), str(self.id_empresa), str(self.id_tienda),
            str(self.id_almacen or ""), str(self.origen or ""), str(self.ref_entidad or ""),
            str(self.ref_id or ""), self.payload_json() or "",
        ])
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "id": self.id, "uuid": self.uuid, "tipo": self.tipo, "prioridad": self.prioridad,
            "estado": self.estado, "id_empresa": self.id_empresa, "id_tienda": self.id_tienda,
            "id_almacen": self.id_almacen, "usuario": self.usuario, "origen": self.origen,
            "destino": self.destino, "version": self.version, "schema_version": self.schema_version,
            "ref_entidad": self.ref_entidad, "ref_id": self.ref_id, "payload": self.payload,
            "observaciones": self.observaciones, "hash": self.hash,
            "fecha_creacion": self.fecha_creacion,
        }
