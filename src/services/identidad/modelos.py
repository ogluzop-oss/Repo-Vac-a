"""
IOC v2 · Identity API — modelos públicos (Bloque 2.1).

La Identity API NUNCA devuelve objetos internos del Repository: envuelve los datos en estos modelos
tipados y estables. Son dataclasses (tipado fuerte, `to_dict()` para serialización) que forman el
contrato público que consumirán los +20 módulos del ERP.
"""

from dataclasses import asdict, dataclass, field


@dataclass
class IdentityReference:
    """Referencia mínima y estable a una entidad de identidad (para listados/enlaces)."""
    uuid: str | None = None
    tipo_entidad: str | None = None   # centro/terminal/impresora/grupo/empresa
    tipo: str | None = None           # tipo funcional (TIENDA/ALMACEN/…)
    nivel: str | None = None
    nombre: str | None = None
    codigo: str | None = None
    estado: str | None = None
    id_empresa: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IdentitySummary:
    """Resumen legible de una identidad (cabecera de ficha)."""
    uuid: str | None = None
    tipo_entidad: str | None = None
    nombre: str | None = None
    nombre_corto: str | None = None
    tipo: str | None = None
    nivel: str | None = None
    estado: str | None = None
    id_empresa: str | None = None
    propietario: str | None = None
    responsable: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IdentityHierarchy:
    """Jerarquía resuelta de una identidad (ascendente y descendente)."""
    uuid: str | None = None
    id_empresa: str | None = None
    ascendentes: list = field(default_factory=list)   # [IdentityReference-like dict]
    descendientes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IdentityResult:
    """Resultado de una resolución: contexto completo + resumen. Contrato público principal."""
    ok: bool = True
    uuid: str | None = None
    id_empresa: str | None = None
    origen: str | None = None
    resumen: dict | None = None        # IdentitySummary.to_dict()
    contexto: dict | None = None       # IdentityContext.to_dict() (empresa/grupo/centro/…)
    error: dict | None = None          # IdentityError.to_dict() si ok=False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IdentitySearchResult:
    """Resultado de una búsqueda: lista de referencias + metadatos."""
    ok: bool = True
    total: int = 0
    id_empresa: str | None = None
    criterio: str | None = None
    resultados: list = field(default_factory=list)   # [IdentityReference.to_dict()]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IdentityError:
    """Error estructurado (equivalente serializable de una IdentityException)."""
    codigo: str = "IDENTITY_ERROR"
    mensaje: str = ""
    entidad: str | None = None
    id_empresa: str | None = None
    detalle: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
