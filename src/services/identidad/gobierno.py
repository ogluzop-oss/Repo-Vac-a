"""
IOC v2 · Gobierno de identidad — reglas oficiales del Identity Core:
  · Ciclo de vida OFICIAL (ACTIVO→SUSPENDIDO→ARCHIVADO→ELIMINACION_PENDIENTE→HISTORICO) con
    transiciones validadas. NUNCA borrado físico (soft delete por transición de estado).
  · Guard de campos INMUTABLES (UUID, empresa propietaria, fecha de creación, identidad raíz).
  · Propiedad y responsabilidad operativa (auditadas).
  · Auditoría ENRIQUECIDA de identidad (valor anterior/nuevo, IP, terminal) que COMPLEMENTA
    `log_auditoria` y el Event Bus (no crea un motor paralelo).
Aditivo: no toca los estados/archivado v1 de `centros_trabajo` (conviven).
"""

import logging

from src.services.identidad import _base as B
from src.services.identidad.tipos import (
    CAMPOS_INMUTABLES, ESTADOS_GOBIERNO, TRANSICIONES_GOBIERNO, valida_estado_gobierno,
)

logger = logging.getLogger("identidad.gobierno")

# Mapeo entidad→(tabla, columna id) para el gobierno genérico.
_ENTIDADES = {
    "centro": ("centros_trabajo", "id_centro"),
    "grupo": ("ioc_grupos_empresariales", "id"),
    "terminal": ("ioc_terminales", "id"),
    "impresora": ("ioc_impresoras", "id"),
}


def es_campo_inmutable(campo) -> bool:
    return campo in CAMPOS_INMUTABLES


def registrar_cambio_auditado(entidad_tipo, entidad_id, campo, valor_anterior, valor_nuevo, *,
                              accion="MODIFICACION", ip=None, id_terminal=None, id_empresa=None) -> bool:
    """Registra un cambio de identidad con valor anterior/nuevo, usuario, IP y terminal. Complementa
    (no sustituye) `log_auditoria` y el Event Bus."""
    id_empresa = B.emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ioc_identidad_auditoria (id_empresa, entidad_tipo, entidad_id, campo, "
                "valor_anterior, valor_nuevo, accion, usuario, ip, id_terminal) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, entidad_tipo, str(entidad_id), campo,
                 None if valor_anterior is None else str(valor_anterior),
                 None if valor_nuevo is None else str(valor_nuevo), accion, B.usuario_actual(),
                 ip, id_terminal))
            conn.commit()
        B.audit("IDENTIDAD_CAMBIO", "ioc_identidad_auditoria", f"{entidad_tipo}:{entidad_id}:{campo}")
        B.evento("identidad.cambio_auditado", ref_entidad=entidad_tipo, ref_id=entidad_id,
                 id_empresa=id_empresa, payload={"campo": campo, "accion": accion})
        return True
    except Exception as e:
        logger.error("registrar_cambio_auditado: %s", e)
        return False


def modificar_atributo(entidad_tipo, entidad_id, campo, valor_nuevo, *, ip=None, id_terminal=None,
                       id_empresa=None) -> dict:
    """Modifica un ATRIBUTO (no identidad) de forma gobernada: rechaza campos inmutables, lee el valor
    anterior, aplica el cambio y lo audita con valor anterior/nuevo."""
    if entidad_tipo not in _ENTIDADES:
        return {"ok": False, "motivo": "entidad no gobernada"}
    if es_campo_inmutable(campo):
        B.audit("IDENTIDAD_INMUTABLE_RECHAZADO", "ioc_identidad_auditoria", f"{entidad_tipo}:{campo}")
        return {"ok": False, "motivo": f"campo inmutable: {campo}"}
    tabla, id_col = _ENTIDADES[entidad_tipo]
    id_empresa = B.emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {campo} FROM {tabla} WHERE {id_col}=%s", (entidad_id,))
            r = cur.fetchone()
            if r is None:
                return {"ok": False, "motivo": "entidad no existe"}
            anterior = r[0] if not isinstance(r, dict) else list(r.values())[0]
            cur.execute(f"UPDATE {tabla} SET {campo}=%s WHERE {id_col}=%s", (valor_nuevo, entidad_id))
            conn.commit()
        registrar_cambio_auditado(entidad_tipo, entidad_id, campo, anterior, valor_nuevo,
                                  ip=ip, id_terminal=id_terminal, id_empresa=id_empresa)
        return {"ok": True, "anterior": anterior, "nuevo": valor_nuevo}
    except Exception as e:
        logger.error("modificar_atributo: %s", e)
        return {"ok": False, "motivo": str(e)}


def estado_actual(entidad_tipo, entidad_id) -> str | None:
    if entidad_tipo not in _ENTIDADES:
        return None
    tabla, id_col = _ENTIDADES[entidad_tipo]
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT estado_gobierno FROM {tabla} WHERE {id_col}=%s", (entidad_id,))
            r = cur.fetchone()
            return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
    except Exception as e:
        logger.debug("estado_actual: %s", e)
        return None


def transicionar_estado(entidad_tipo, entidad_id, nuevo_estado, *, ip=None, id_terminal=None,
                        id_empresa=None) -> dict:
    """Cambia el estado oficial validando la transición. Es la ÚNICA vía de 'eliminación' (soft):
    nunca se ejecuta un DELETE físico."""
    if entidad_tipo not in _ENTIDADES:
        return {"ok": False, "motivo": "entidad no gobernada"}
    nuevo = valida_estado_gobierno(nuevo_estado)
    actual = estado_actual(entidad_tipo, entidad_id) or "ACTIVO"
    if nuevo == actual:
        return {"ok": True, "estado": nuevo, "sin_cambio": True}
    permitidas = TRANSICIONES_GOBIERNO.get(actual, ())
    if nuevo not in permitidas:
        return {"ok": False, "motivo": f"transición no permitida {actual}→{nuevo}",
                "permitidas": list(permitidas)}
    tabla, id_col = _ENTIDADES[entidad_tipo]
    id_empresa = B.emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE {tabla} SET estado_gobierno=%s WHERE {id_col}=%s", (nuevo, entidad_id))
            conn.commit()
        registrar_cambio_auditado(entidad_tipo, entidad_id, "estado_gobierno", actual, nuevo,
                                  accion="TRANSICION_ESTADO", ip=ip, id_terminal=id_terminal,
                                  id_empresa=id_empresa)
        return {"ok": True, "estado": nuevo, "anterior": actual}
    except Exception as e:
        logger.error("transicionar_estado: %s", e)
        return {"ok": False, "motivo": str(e)}


def soft_delete(entidad_tipo, entidad_id, **kw) -> dict:
    """'Eliminación' oficial = transición a ELIMINACION_PENDIENTE. Nunca borra físicamente."""
    return transicionar_estado(entidad_tipo, entidad_id, "ELIMINACION_PENDIENTE", **kw)


def set_propiedad(entidad_tipo, entidad_id, *, id_propietario=None, id_responsable_operativo=None,
                  ip=None, id_terminal=None, id_empresa=None) -> dict:
    """Asigna propietario y/o responsable operativo (auditado). Solo aplica a entidades con esas
    columnas (centro/grupo)."""
    if entidad_tipo not in ("centro", "grupo"):
        return {"ok": False, "motivo": "entidad sin propiedad gobernada"}
    resultados = {}
    if id_propietario is not None:
        resultados["propietario"] = modificar_atributo(
            entidad_tipo, entidad_id, "id_propietario", id_propietario,
            ip=ip, id_terminal=id_terminal, id_empresa=id_empresa)
    if id_responsable_operativo is not None and entidad_tipo == "centro":
        resultados["responsable"] = modificar_atributo(
            entidad_tipo, entidad_id, "id_responsable_operativo", id_responsable_operativo,
            ip=ip, id_terminal=id_terminal, id_empresa=id_empresa)
    ok = all(r.get("ok") for r in resultados.values()) if resultados else False
    return {"ok": ok, **resultados}


def historial_identidad(entidad_tipo, entidad_id, *, limite=200) -> list:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ioc_identidad_auditoria WHERE entidad_tipo=%s AND entidad_id=%s "
                        "ORDER BY fecha DESC, id DESC LIMIT %s", (entidad_tipo, str(entidad_id), int(limite)))
            return B.filas(cur)
    except Exception as e:
        logger.error("historial_identidad: %s", e)
        return []


def estados_oficiales() -> tuple:
    return ESTADOS_GOBIERNO
