"""
Videovigilancia — servicios de cámaras de seguridad (API-First, sin PyQt).

    from src.services import camaras
    cid = camaras.crear_camara("Entrada", id_empresa=..., id_centro="1", tipo_centro="tienda")
    camaras.grabar_dia(cam, duracion_seg=1)             # graba el fichero del día (degradable)
    camaras.fechas_disponibles(cid, id_empresa=...)     # días con grabación
    camaras.extraer_clip(cid, "2026-07-12", inicio_seg=1, fin_seg=3, id_empresa=...)

Aislamiento ESTRICTO por empresa+departamento; SUPERADMIN puede cruzar (permitir_super).
"""

from src.services.camaras.registro import (  # noqa: F401
    crear_camara, renombrar_camara, eliminar_camara, actualizar_fuente, listar_camaras, obtener_camara,
    departamentos,
)
from src.services.camaras.grabacion import (  # noqa: F401
    grabar_dia, ruta_dia, RecorderService, servicio as recorder,
)
from src.services.camaras.reproduccion import (  # noqa: F401
    grabacion_de, fechas_disponibles, extraer_clip,
)
from src.services.camaras.deteccion import (  # noqa: F401
    listar_eventos, analizar_grabacion,
)
from src.services.camaras.ptz import (  # noqa: F401
    mover as ptz_mover, capacidades as ptz_capacidades, disponible as ptz_disponible,
)
from src.services.camaras.orquestacion import (  # noqa: F401
    terminal_id, propietario as grabador_propietario,
)

__all__ = ["crear_camara", "renombrar_camara", "eliminar_camara", "actualizar_fuente", "listar_camaras",
           "obtener_camara", "departamentos", "grabar_dia", "ruta_dia", "RecorderService", "recorder",
           "grabacion_de", "fechas_disponibles", "extraer_clip", "listar_eventos", "analizar_grabacion",
           "ptz_mover", "ptz_capacidades", "ptz_disponible", "terminal_id", "grabador_propietario"]
