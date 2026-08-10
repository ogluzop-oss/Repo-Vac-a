"""
Variables what-if de un escenario (Paquete Enterprise 9, SUBFASE 9.3). Registra las alteraciones
VIRTUALES (precio/descuento/promocion/salario/plantilla/stock/proveedor/impuestos/gastos/tiendas/
almacenes) dentro de un escenario. Nunca altera datos reales.
"""

import json
import logging

from src.services.simulador import base as B
from src.services.simulador import propagacion as P

logger = logging.getLogger("simulador.variables")

# Mapa variable → dominio (para la confianza y el enrutado a agentes).
DOMINIO_DE = {
    "precio": "comercial", "descuento": "comercial", "promocion": "comercial",
    "salario": "rrhh", "plantilla": "rrhh",
    "stock": "logistica", "proveedor": "logistica", "almacenes": "logistica",
    "impuestos": "fiscal", "gastos": "financiera", "tiendas": "estructura",
}


def añadir(id_escenario, variable, valor, *, operacion="delta_pct", params=None, id_empresa=None) -> bool:
    if variable not in P.VARIABLES:
        logger.debug("variable no soportada: %s", variable)
        return False
    emp = B._emp(id_empresa)
    dominio = DOMINIO_DE.get(variable, "comercial")
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO sim_variables (id_escenario, id_empresa, dominio, variable, "
                        "operacion, valor, params_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (id_escenario, emp, dominio, variable, operacion, float(valor),
                         json.dumps(params, default=str) if params else None))
            c.commit()
            return True
    except Exception as e:
        logger.error("añadir variable: %s", e)
        return False


def listar(id_escenario, id_empresa=None) -> list:
    emp = B._emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT dominio, variable, operacion, valor FROM sim_variables "
                        "WHERE id_escenario=%s AND id_empresa=%s ORDER BY id", (id_escenario, emp))
            filas = _filas_a_dicts(cur, cur.fetchall())
            for f in filas:
                f["valor"] = float(f.get("valor") or 0)
            return filas
    except Exception as e:
        logger.error("listar variables: %s", e)
        return []
