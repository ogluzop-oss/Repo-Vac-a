"""
Business Process Designer (Fase V · Bloque 4) — fachada.

Diseñador visual de procesos que REUTILIZA el Workflow Engine existente (no crea un segundo motor).
Paleta de bloques (inicio/fin/condición/aprobación/firma/comunicación/esperar/temporizador/webhook/
evento/script/incidencia/documento/workflow-hijo/regla), diseño versionado (borrador/publicado/
rollback) y compilación → Workflow. Multiempresa.

    from src.services import bpd
    pid = bpd.crear_proceso("factura_flow", "Flujo de factura", id_empresa=emp)
    bpd.guardar_borrador(pid, {"nodos": [...], "aristas": [...]}, id_empresa=emp)
    bpd.publicar(pid, 1, id_empresa=emp)
    bpd.compilar_proceso(pid, id_empresa=emp)      # → definición Workflow
"""

from src.services.bpd.bloques import BLOQUES, TIPOS, paleta, es_valido, destino  # noqa: F401
from src.services.bpd.diseno import (  # noqa: F401
    crear_proceso, validar_definicion, guardar_borrador, publicar, rollback, obtener_version,
    listar_procesos, definicion_de,
)
from src.services.bpd.compilador import compilar, compilar_proceso, ejecutar  # noqa: F401

__all__ = ["BLOQUES", "TIPOS", "paleta", "es_valido", "destino", "crear_proceso",
           "validar_definicion", "guardar_borrador", "publicar", "rollback", "obtener_version",
           "listar_procesos", "definicion_de", "compilar", "compilar_proceso", "ejecutar"]
