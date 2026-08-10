"""
Enumeraciones de la Identidad Operativa de Centros (IOC). Definidas como tuplas/inmutables para no
introducir dependencias; la arquitectura queda preparada para todos los tipos sin cambios futuros.
"""

# Tipos de centro operativo (jerarquía representable: empresa→centro→instalación→unidad→terminal→usuario).
TIPOS_CENTRO = (
    "TIENDA", "ALMACEN", "OFICINA", "CENTRO_LOGISTICO", "CENTRO_SAT", "CENTRO_RRHH",
    "CENTRO_FINANCIERO", "CENTRO_PRODUCCION", "CENTRO_CALIDAD", "SHOWROOM", "DELEGACION",
    "PLATAFORMA", "DARK_STORE", "FABRICA", "CENTRO_ADMINISTRATIVO", "CENTRO_FORMACION",
    "CENTRO_IDI", "OTRO",
)

# Códigos operativos independientes (nunca reutilizar un campo para varios propósitos).
TIPOS_CODIGO = (
    "VISIBLE", "INTERNO", "CORTO", "FISCAL", "CONTABLE", "LOGISTICO", "RRHH", "TPV",
    "DOCUMENTAL", "BI", "INTEGRACION",
)

# Tipos de dispositivo/terminal.
TIPOS_DISPOSITIVO = ("TPV", "PDA", "MOVIL", "INDUSTRIAL", "KIOSCO", "BALANZA", "OTRO")

# Tipos de impresora.
TIPOS_IMPRESORA = ("TICKETS", "ETIQUETAS", "A4", "ALMACEN", "COCINA", "OTRO")

# Estados comunes (dispositivos/terminales).
ESTADOS = ("ACTIVO", "INACTIVO", "MANTENIMIENTO", "BAJA")

# ── IOC v2 · Gobierno de identidad ────────────────────────────────────────────
# Ciclo de vida OFICIAL de una identidad (nunca borrado físico: soft delete por transición).
ESTADOS_GOBIERNO = ("ACTIVO", "SUSPENDIDO", "ARCHIVADO", "ELIMINACION_PENDIENTE", "HISTORICO")

# Transiciones permitidas del ciclo de vida oficial.
TRANSICIONES_GOBIERNO = {
    "ACTIVO": ("SUSPENDIDO", "ARCHIVADO", "ELIMINACION_PENDIENTE"),
    "SUSPENDIDO": ("ACTIVO", "ARCHIVADO", "ELIMINACION_PENDIENTE"),
    "ARCHIVADO": ("ACTIVO", "ELIMINACION_PENDIENTE", "HISTORICO"),
    "ELIMINACION_PENDIENTE": ("ARCHIVADO", "HISTORICO"),
    "HISTORICO": (),  # terminal: no se reactiva ni se borra
}

# Niveles de la jerarquía corporativa (extensible sin rediseño del núcleo).
NIVELES = ("GRUPO", "EMPRESA", "CENTRO", "SUBCENTRO", "ZONA")

# Tipos de grupo empresarial (nivel superior).
TIPOS_GRUPO = ("HOLDING", "GRUPO", "FRANQUICIA")

# Campos que JAMÁS pueden modificarse (identidad permanente).
CAMPOS_INMUTABLES = ("id", "id_centro", "id_empresa", "fecha_creacion", "fecha_alta")


def valida_nivel(n): return (n or "CENTRO").upper() if (n or "CENTRO").upper() in NIVELES else "CENTRO"
def valida_estado_gobierno(e): return (e or "ACTIVO").upper() if (e or "ACTIVO").upper() in ESTADOS_GOBIERNO else "ACTIVO"
def valida_tipo_grupo(t): return (t or "GRUPO").upper() if (t or "GRUPO").upper() in TIPOS_GRUPO else "GRUPO"


def valida_tipo_centro(t): return (t or "OTRO").upper() if (t or "OTRO").upper() in TIPOS_CENTRO else "OTRO"
def valida_tipo_codigo(t): return (t or "").upper() if (t or "").upper() in TIPOS_CODIGO else None
def valida_tipo_dispositivo(t): return (t or "TPV").upper() if (t or "TPV").upper() in TIPOS_DISPOSITIVO else "OTRO"
def valida_tipo_impresora(t): return (t or "TICKETS").upper() if (t or "TICKETS").upper() in TIPOS_IMPRESORA else "OTRO"
