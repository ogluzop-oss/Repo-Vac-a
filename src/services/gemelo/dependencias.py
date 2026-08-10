"""
Grafo de dependencias del Gemelo Digital (Paquete Enterprise 8, SUBFASE 8.8).

El sistema conoce las relaciones entre entidades y puede recorrer la cadena de valor:

    pedido → proveedor → recepcion → stock → venta → factura → cobro → contabilidad

Cada arista se persiste en `dt_dependencias` (idempotente). Se puede recorrer hacia adelante
(descendientes) y hacia atras (ascendientes). El registro de aristas se alimenta principalmente
desde el Event Bus (ver eventos_twin), nunca por llamadas manuales entre modulos.
"""

import logging

from src.services.gemelo import fuentes as F

logger = logging.getLogger("gemelo.dependencias")

# Cadena canonica de la trazabilidad operativa (para documentacion y validacion de consistencia).
CADENA_VALOR = ["pedido", "proveedor", "recepcion", "stock", "venta", "factura", "cobro",
                "contabilidad"]


def registrar(origen_entidad, origen_id, destino_entidad, destino_id, *, relacion="deriva_en",
              id_empresa=None, origen_evento=None) -> bool:
    """Registra (idempotente) una arista de dependencia. BULLETPROOF: nunca rompe el flujo."""
    if origen_id is None or destino_id is None:
        return False
    emp = F.emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO dt_dependencias (id_empresa, origen_entidad, origen_id, "
                "destino_entidad, destino_id, relacion, origen_evento) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE origen_evento=COALESCE(VALUES(origen_evento), origen_evento)",
                (emp, str(origen_entidad)[:40], str(origen_id)[:80], str(destino_entidad)[:40],
                 str(destino_id)[:80], str(relacion)[:40], origen_evento))
            c.commit()
            return True
    except Exception as e:
        logger.debug("registrar dependencia: %s", e)
        return False


def descendientes(entidad, entidad_id, *, id_empresa=None, profundidad=6) -> list:
    """Recorre la cadena hacia adelante desde una entidad (que se deriva de esto)."""
    return _recorrer(entidad, entidad_id, "adelante", id_empresa, profundidad)


def ascendientes(entidad, entidad_id, *, id_empresa=None, profundidad=6) -> list:
    """Recorre la cadena hacia atras (de que proviene esto)."""
    return _recorrer(entidad, entidad_id, "atras", id_empresa, profundidad)


def _recorrer(entidad, entidad_id, sentido, id_empresa, profundidad) -> list:
    emp = F.emp(id_empresa)
    visitados = set()
    resultado = []
    frontera = [(str(entidad), str(entidad_id), 0)]
    while frontera:
        ent, eid, nivel = frontera.pop(0)
        clave = (ent, eid)
        if clave in visitados or nivel >= profundidad:
            continue
        visitados.add(clave)
        if sentido == "adelante":
            filas = F.filas("SELECT destino_entidad e, destino_id i, relacion r FROM dt_dependencias "
                            "WHERE id_empresa=%s AND origen_entidad=%s AND origen_id=%s",
                            (emp, ent, eid))
        else:
            filas = F.filas("SELECT origen_entidad e, origen_id i, relacion r FROM dt_dependencias "
                            "WHERE id_empresa=%s AND destino_entidad=%s AND destino_id=%s",
                            (emp, ent, eid))
        for f in filas:
            paso = {"desde": {"entidad": ent, "id": eid}, "relacion": f.get("r"),
                    "hacia": {"entidad": f.get("e"), "id": str(f.get("i"))}, "nivel": nivel + 1}
            resultado.append(paso)
            frontera.append((str(f.get("e")), str(f.get("i")), nivel + 1))
    return resultado


def cadena(entidad, entidad_id, *, id_empresa=None) -> dict:
    """Traza completa (ascendientes + descendientes) de una entidad para el visor de dependencias."""
    return {
        "entidad": {"entidad": str(entidad), "id": str(entidad_id)},
        "origen": ascendientes(entidad, entidad_id, id_empresa=id_empresa),
        "consecuencias": descendientes(entidad, entidad_id, id_empresa=id_empresa),
    }
