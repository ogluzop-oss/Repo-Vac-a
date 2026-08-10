"""
Cadenas de aprobacion corporativas (Paquete Enterprise 7, SUBFASE 7.3). Define reglas del tipo
"Compras > 5.000 € → Responsable tienda → Director regional → Central → Direccion financiera".
REUTILIZA Workflow/BPM (no crea un motor nuevo): la cadena solo determina QUIEN aprueba; el
circuito lo lleva el Workflow existente.
"""

import json
import logging
import re

logger = logging.getLogger("gobierno.aprobaciones")

# Catalogo semilla de cadenas (global, id_empresa NULL). cadena = secuencia de roles organicos.
CATALOGO = [
    {"codigo": "APR_COMPRAS_5000", "entidad": "compras", "condicion": "importe>5000",
     "cadena": ["principal", "director", "administrador"]},
    {"codigo": "APR_FACTURA_10000", "entidad": "factura", "condicion": "importe>10000",
     "cadena": ["director", "administrador"]},
    {"codigo": "APR_GASTO_1000", "entidad": "gasto", "condicion": "importe>1000",
     "cadena": ["principal", "supervisor"]},
]


def _emp(id_empresa=None):
    from src.services.gobierno import organigrama as _O
    return _O._emp(id_empresa)


def sembrar(cur) -> int:
    n = 0
    for r in CATALOGO:
        cur.execute("SELECT 1 FROM org_aprobacion_reglas WHERE id_empresa IS NULL AND codigo=%s",
                    (r["codigo"],))
        if cur.fetchone():
            continue
        cur.execute("INSERT INTO org_aprobacion_reglas (id_empresa, codigo, entidad, condicion, "
                    "cadena, activa) VALUES (NULL,%s,%s,%s,%s,1)",
                    (r["codigo"], r["entidad"], r["condicion"], json.dumps(r["cadena"])))
        n += 1
    return n


def _cumple(condicion, valor) -> bool:
    m = re.match(r"\s*(\w+)\s*([<>]=?|=)\s*([\d.]+)", condicion or "")
    if not m:
        return True
    _campo, op, num = m.groups()
    try:
        v, num = float(valor or 0), float(num)
    except Exception:
        return True
    return {">": v > num, ">=": v >= num, "<": v < num, "<=": v <= num, "=": v == num}.get(op, True)


def cadena_para(entidad, valor=0, id_empresa=None) -> dict | None:
    """Regla de aprobacion aplicable a (entidad, valor). Devuelve {codigo, cadena, condicion}."""
    emp = _emp(id_empresa)
    reglas = []
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM org_aprobacion_reglas WHERE activa=1 AND entidad=%s "
                        "AND (id_empresa IS NULL OR id_empresa=%s)", (entidad, emp))
            reglas = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("cadena_para: %s", e)
    if not reglas:
        reglas = [r for r in CATALOGO if r["entidad"] == entidad]
    for r in reglas:
        if _cumple(r.get("condicion"), valor):
            cadena = r.get("cadena")
            if isinstance(cadena, str):
                try:
                    cadena = json.loads(cadena)
                except Exception:
                    cadena = []
            return {"codigo": r.get("codigo"), "cadena": cadena or [], "condicion": r.get("condicion")}
    return None


def iniciar_aprobacion(entidad, entidad_id, *, importe=0, id_empresa=None, actor=None) -> dict:
    """Determina la cadena y lanza el Workflow/BPM existente (no crea motor nuevo)."""
    emp = _emp(id_empresa)
    regla = cadena_para(entidad, importe, emp)
    wf = {}
    try:
        from src.services.workflow import workflow_engine as WF
        wf = WF.iniciar_proceso(entidad, entidad_id, contexto={"importe": importe},
                                actor=actor, id_empresa=emp)
    except Exception as e:
        logger.debug("iniciar workflow: %s", e)
    return {"entidad": entidad, "entidad_id": entidad_id, "importe": importe,
            "cadena": (regla or {}).get("cadena", []), "regla": (regla or {}).get("codigo"),
            "workflow": wf}
