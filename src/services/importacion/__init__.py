"""
Importador maestro — motor de ingesta de datos de empresa (API-First, sin PyQt).

Migra datos MAESTROS + saldos iniciales desde casi cualquier formato a los motores oficiales de Smart Manager,
sin recrear nada a mano. Fase 1: universal (CSV/TSV/TXT · Excel · JSON/JSONL) → productos + familias + stock.

    from src.services import importacion
    plan = importacion.analizar("catalogo.xlsx")          # columnas + mapeo sugerido (para confirmar)
    informe = importacion.simular("catalogo.xlsx")        # dry-run: nuevos/actualizados/errores
    res = importacion.ejecutar("catalogo.xlsx", id_empresa=...)   # carga real, idempotente

Reglas: toda la lógica vive aquí (no en la GUI); la carga usa EXCLUSIVAMENTE db/articulos + db/familias +
db/stock + db/kardex (N7); multi-tenant estricto por id_empresa.
"""

from src.services.importacion.modelo import (  # noqa: F401
    CLIENTES, ENTIDADES, PRODUCTOS, PROVEEDORES, SALDOS, TESORERIA, VENTAS_HIST,
)
from src.services.importacion.lectores import FORMATOS, detectar_formato, leer  # noqa: F401
from src.services.importacion.mapeo import sugerir_mapeo  # noqa: F401
from src.services.importacion.retail import leer_bmecat, leer_edifact_pricat  # noqa: F401
from src.services.importacion.dump_sql import leer_sql_dump, tablas_dump  # noqa: F401
from src.services.importacion.conector import leer_consulta, leer_odbc, leer_api  # noqa: F401
from src.services.importacion.mapeo_ia import sugerir_mapeo_ia, disponible as ia_disponible  # noqa: F401
from src.services.importacion.motor import (  # noqa: F401
    analizar, simular, ejecutar, analizar_filas, simular_filas, ejecutar_filas,
    importar_desde_bd, importar_desde_odbc, importar_desde_api, trabajos_recientes, importar_documentos,
)

__all__ = ["PRODUCTOS", "CLIENTES", "PROVEEDORES", "VENTAS_HIST", "SALDOS", "TESORERIA", "ENTIDADES",
           "FORMATOS", "detectar_formato", "leer", "sugerir_mapeo", "sugerir_mapeo_ia", "ia_disponible",
           "analizar", "simular", "ejecutar", "analizar_filas", "simular_filas", "ejecutar_filas",
           "leer_bmecat", "leer_edifact_pricat", "leer_sql_dump", "tablas_dump", "leer_consulta",
           "leer_odbc", "leer_api", "importar_desde_bd", "importar_desde_odbc", "importar_desde_api",
           "trabajos_recientes", "importar_documentos"]
