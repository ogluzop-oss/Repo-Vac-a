"""
Plantillas de circuitos por dominio (FASE WF-5..WF-10).

Crea (idempotente, por empresa) definiciones de workflow para las entidades clave del ERP,
usando permisos del RBAC. Son el punto de partida configurable por el diseñador; cada empresa
puede modificarlas. Entidades cubiertas: compras_pedido, tesoreria_pago, tesoreria_transferencia,
rrhh_vacaciones, contabilidad_cierre, aeat_modelo, documento.
"""

import logging

from src.db import workflow as _W

logger = logging.getLogger("workflow.plantillas")

# entidad → (codigo, nombre, [pasos], [reglas])
# paso: dict(orden, nombre, permiso?/rol?/grupo?, usuarios_minimos?, sla_horas?)
# regla: (orden_paso, condicion, operador, valor)  → activar_paso si se cumple
PLANTILLAS = {
    "compras_pedido": {
        "codigo": "WF_COMPRAS_PEDIDO", "nombre": "Aprobación de pedido de compra",
        "pasos": [
            {"orden": 10, "nombre": "Aprobación responsable", "permiso": "compras.aprobar", "sla_horas": 48},
            {"orden": 20, "nombre": "Segunda aprobación", "permiso": "compras.aprobar", "sla_horas": 48},
            {"orden": 30, "nombre": "Gerencia", "rol": "GERENTE", "sla_horas": 72},
        ],
        "reglas": [(10, "importe", ">=", 500), (20, "importe", ">=", 5000), (30, "importe", ">=", 20000)],
    },
    "tesoreria_pago": {
        "codigo": "WF_TESO_PAGO", "nombre": "Aprobación de pago a proveedor",
        "pasos": [
            {"orden": 10, "nombre": "Aprobación tesorería", "permiso": "tesoreria.movimientos", "sla_horas": 24},
            {"orden": 20, "nombre": "Doble aprobación", "rol": "GERENTE", "sla_horas": 48},
        ],
        "reglas": [(10, "importe", ">=", 1000), (20, "importe", ">=", 10000)],
    },
    "tesoreria_transferencia": {
        "codigo": "WF_TESO_TRF", "nombre": "Aprobación de transferencia",
        "pasos": [
            {"orden": 10, "nombre": "Aprobación tesorería", "permiso": "tesoreria.movimientos", "sla_horas": 24},
            {"orden": 20, "nombre": "Doble aprobación", "rol": "GERENTE", "sla_horas": 48},
        ],
        "reglas": [(10, "importe", ">=", 1000), (20, "importe", ">=", 10000)],
    },
    "rrhh_vacaciones": {
        "codigo": "WF_RRHH_VAC", "nombre": "Aprobación de vacaciones",
        "pasos": [{"orden": 10, "nombre": "Aprobación RRHH", "permiso": "rrhh.editar", "sla_horas": 72}],
        "reglas": [],
    },
    "contabilidad_cierre": {
        "codigo": "WF_CONTAB_CIERRE", "nombre": "Aprobación de cierre contable",
        "pasos": [
            {"orden": 10, "nombre": "Contabilidad", "permiso": "contabilidad.cierre", "sla_horas": 48},
            {"orden": 20, "nombre": "Gerencia", "rol": "GERENTE", "sla_horas": 72},
        ],
        "reglas": [],
    },
    "aeat_modelo": {
        "codigo": "WF_AEAT", "nombre": "Revisión y presentación AEAT",
        "pasos": [
            {"orden": 10, "nombre": "Revisión", "permiso": "aeat.generar", "sla_horas": 48},
            {"orden": 20, "nombre": "Aprobación presentación", "permiso": "aeat.presentar", "sla_horas": 48},
        ],
        "reglas": [],
    },
    "documento": {
        "codigo": "WF_DOC", "nombre": "Aprobación documental",
        "pasos": [
            {"orden": 10, "nombre": "Revisión", "permiso": "documentos.ver", "sla_horas": 72},
            {"orden": 20, "nombre": "Aprobación", "permiso": "documentos.exportar", "sla_horas": 72},
        ],
        "reglas": [],
    },
}


def crear_plantilla(entidad, id_empresa=None) -> int | None:
    """Crea (idempotente) la definición de una entidad con sus pasos y reglas."""
    cfg = PLANTILLAS.get(entidad)
    if not cfg:
        return None
    did = _W.crear_definicion(cfg["codigo"], cfg["nombre"], entidad, id_empresa=id_empresa)
    if not did:
        return None
    # Evita duplicar pasos si ya existen.
    if _W.pasos_de(did):
        return did
    orden_a_id = {}
    for p in cfg["pasos"]:
        pid = _W.anadir_paso(did, p["orden"], p["nombre"], permiso_requerido=p.get("permiso"),
                             rol_requerido=p.get("rol"), grupo_requerido=p.get("grupo"),
                             usuarios_minimos=p.get("usuarios_minimos", 1), sla_horas=p.get("sla_horas"))
        orden_a_id[p["orden"]] = pid
    for (orden_paso, cond, op, val) in cfg["reglas"]:
        _W.anadir_regla(did, cond, op, val, id_paso=orden_a_id.get(orden_paso))
    return did


def seed_plantillas(id_empresa=None) -> dict:
    """Crea todas las plantillas por defecto de la empresa. Idempotente."""
    res = {}
    for entidad in PLANTILLAS:
        res[entidad] = crear_plantilla(entidad, id_empresa=id_empresa)
    return res
