"""
Persistencia real de Integraciones Comerciales (petición explícita, 2026-11-24 — ver migración
0362). Una fila por (id_empresa, plataforma): metadatos de conexión con un canal externo
(WooCommerce/Shopify/Amazon/...). **Nunca credenciales reales**: `credenciales_ref` es solo el
NOMBRE del secreto en Secret Manager (ver `services.marketplace.integraciones_comerciales.modelo
.Integracion`, que sigue siendo el objeto de valor en memoria — esta capa solo lo hace sobrevivir
a un reinicio). Antes de esta migración, `servicio.py` guardaba todo esto en un diccionario Python
en memoria (`_REGISTRO`), perdido en cada reinicio del backend.
"""

import datetime
import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("ic_integraciones_db")

_CAMPOS = ("nombre", "tipo", "estado", "url", "version", "ultima_sync", "frecuencia",
          "observaciones", "credenciales_ref", "habilitada", "creado")


def _fila_a_dict(cur, fila) -> dict:
    if isinstance(fila, dict):
        return dict(fila)
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, fila))


def obtener(id_empresa, plataforma) -> dict | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM ic_integraciones WHERE id_empresa=%s AND plataforma=%s",
                (str(id_empresa), (plataforma or "").lower()))
            r = cur.fetchone()
            return _fila_a_dict(cur, r) if r else None
    except Exception as e:
        logger.error("obtener(%s, %s): %s", id_empresa, plataforma, e)
        return None


def listar(id_empresa) -> list[dict]:
    """Integraciones de UNA empresa (aislamiento estricto: nunca de otro tenant)."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ic_integraciones WHERE id_empresa=%s", (str(id_empresa),))
            return [_fila_a_dict(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar(%s): %s", id_empresa, e)
        return []


def listar_activas_todas_empresas() -> list[dict]:
    """Integraciones OPERATIVAS de CUALQUIER empresa (`habilitada=1` + referencia de credenciales
    presente) — para el sondeo periódico de pedidos entrantes (ver
    `services.marketplace.integraciones_comerciales.sync_worker
    .importar_pedidos_canales_activos`), que es transversal a todos los tenants."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM ic_integraciones WHERE habilitada=1 "
                "AND credenciales_ref IS NOT NULL AND credenciales_ref<>''")
            return [_fila_a_dict(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_activas_todas_empresas: %s", e)
        return []


def guardar(datos: dict) -> bool:
    """Upsert por (id_empresa, plataforma). `datos` debe incluir id_empresa/plataforma y puede
    incluir cualquiera de `_CAMPOS` (los omitidos quedan NULL/por defecto en una fila nueva, o SIN
    TOCAR en una ya existente — mismo criterio de upsert parcial que `db.datafono.guardar_config`:
    aquí se construye la fila completa ANTES de llamar, a diferencia de ese módulo, porque
    `servicio.py` ya tiene el objeto `Integracion` completo en memoria en cada escritura)."""
    id_empresa = str(datos["id_empresa"])
    plataforma = (datos["plataforma"] or "").lower()
    creado = datos.get("creado")
    if isinstance(creado, (int, float)):
        creado = datetime.datetime.fromtimestamp(creado)
    ultima_sync = datos.get("ultima_sync")
    if isinstance(ultima_sync, (int, float)):
        ultima_sync = datetime.datetime.fromtimestamp(ultima_sync)
    vals = {
        "nombre": datos.get("nombre"), "tipo": datos.get("tipo"), "estado": datos.get("estado"),
        "url": datos.get("url"), "version": datos.get("version"), "ultima_sync": ultima_sync,
        "frecuencia": datos.get("frecuencia"), "observaciones": datos.get("observaciones"),
        "credenciales_ref": datos.get("credenciales_ref"),
        "habilitada": 1 if datos.get("habilitada", True) else 0, "creado": creado,
    }
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ic_integraciones (id_empresa, plataforma, nombre, tipo, estado, url, "
                "version, ultima_sync, frecuencia, observaciones, credenciales_ref, habilitada, "
                "creado) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "nombre=VALUES(nombre), tipo=VALUES(tipo), estado=VALUES(estado), "
                "url=VALUES(url), version=VALUES(version), ultima_sync=VALUES(ultima_sync), "
                "frecuencia=VALUES(frecuencia), observaciones=VALUES(observaciones), "
                "credenciales_ref=VALUES(credenciales_ref), habilitada=VALUES(habilitada)",
                (id_empresa, plataforma, vals["nombre"], vals["tipo"], vals["estado"], vals["url"],
                 vals["version"], vals["ultima_sync"], vals["frecuencia"], vals["observaciones"],
                 vals["credenciales_ref"], vals["habilitada"], vals["creado"]))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar(%s, %s): %s", id_empresa, plataforma, e)
        return False


def eliminar(id_empresa, plataforma) -> bool:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ic_integraciones WHERE id_empresa=%s AND plataforma=%s",
                       (str(id_empresa), (plataforma or "").lower()))
            afectadas = cur.rowcount
            conn.commit()
        return afectadas > 0
    except Exception as e:
        logger.error("eliminar(%s, %s): %s", id_empresa, plataforma, e)
        return False


def borrar_todo() -> None:
    """SOLO para el reset de tests (`servicio._reset_para_tests`) — mismo efecto de vaciado total
    que el `_REGISTRO.clear()` que sustituye, sin reducir el aislamiento ya existente entre tests."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ic_integraciones")
            conn.commit()
    except Exception as e:
        logger.error("borrar_todo: %s", e)
