"""
RGPD (SEC-9): derecho de acceso, portabilidad, derecho al olvido (anonimización) y registro de
solicitudes. Multiempresa y auditado. La anonimización es reversible solo a nivel de copia (no
borra registros fiscales/contables con valor legal: los anonimiza preservando la integridad).
"""

import datetime as _dt
import json
import logging
import os

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("seguridad.rgpd")
TIPOS = ("acceso", "portabilidad", "olvido")
# Campos personales que se anonimizan en el derecho al olvido (preservando el registro).
_ANONIMIZAR = {
    "clientes": ["nombre", "nif", "telefono", "email", "direccion"],
    "ventas": ["cliente_nombre", "cliente_nif"],
    "facturas_cliente": [],   # se conservan por obligación fiscal; solo se desvincula el cliente
}


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _dir():
    base = os.path.join("documentos", "rgpd")
    try:
        from src.utils.recursos import ruta_datos
        base = ruta_datos("rgpd")
    except Exception:
        pass
    os.makedirs(base, exist_ok=True)
    return base


def _registrar(tipo, sujeto_tipo, sujeto_id, sujeto_nif, estado, ruta, solicitante, id_empresa):
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO rgpd_solicitudes (id_empresa, tipo, sujeto_tipo, sujeto_id, "
                        "sujeto_nif, estado, resultado_ruta, solicitante, resuelto_en) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, tipo, sujeto_tipo, sujeto_id, sujeto_nif, estado, ruta, solicitante,
                         _dt.datetime.now() if estado == "resuelta" else None))
            sid = cur.lastrowid
            conn.commit()
        _audit(f"RGPD_{tipo.upper()}", f"{sujeto_tipo}:{sujeto_id or sujeto_nif} → {estado}")
        return sid
    except Exception as e:
        logger.error("_registrar: %s", e)
        return None


def _datos_cliente(id_cliente, id_empresa):
    """Recopila los datos personales de un cliente en todas las tablas relevantes."""
    datos = {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM clientes WHERE id=%s AND id_empresa=%s", (id_cliente, id_empresa))
            r = cur.fetchone()
            if r:
                datos["cliente"] = r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))
            cur.execute("SELECT id, fecha, total, cliente_nombre, cliente_nif FROM ventas "
                        "WHERE id_empresa=%s AND cliente_id=%s LIMIT 1000", (id_empresa, id_cliente))
            datos["ventas"] = [(x if isinstance(x, dict) else dict(zip([d[0] for d in cur.description], x)))
                               for x in cur.fetchall()]
    except Exception as e:
        logger.error("_datos_cliente: %s", e)
    return datos


def acceso(id_cliente, *, id_empresa=None, solicitante=None) -> dict:
    """Derecho de acceso/portabilidad: exporta los datos personales del sujeto a JSON."""
    id_empresa = _emp(id_empresa)
    datos = _datos_cliente(id_cliente, id_empresa)
    ruta = os.path.join(_dir(), f"rgpd_acceso_{id_empresa}_{id_cliente}_{_dt.datetime.now():%Y%m%d%H%M%S}.json")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"id_empresa": id_empresa, "id_cliente": id_cliente, "fecha": _dt.datetime.now().isoformat(),
                       "datos": datos}, f, ensure_ascii=False, default=str, indent=2)
    except Exception as e:
        logger.error("acceso: %s", e)
        ruta = None
    sid = _registrar("acceso", "cliente", id_cliente, (datos.get("cliente") or {}).get("nif"),
                     "resuelta" if ruta else "error", ruta, solicitante, id_empresa)
    return {"ok": bool(ruta), "ruta": ruta, "solicitud": sid}


def portabilidad(id_cliente, *, id_empresa=None, solicitante=None) -> dict:
    """Portabilidad = exportación estructurada (JSON). Reutiliza acceso."""
    r = acceso(id_cliente, id_empresa=id_empresa, solicitante=solicitante)
    return r


def olvido(id_cliente, *, id_empresa=None, solicitante=None) -> dict:
    """Derecho al olvido: ANONIMIZA los datos personales del cliente preservando los registros
    con valor legal (facturas/ventas se conservan, pero se anonimiza la identificación)."""
    id_empresa = _emp(id_empresa)
    anon = f"ANONIMIZADO-{id_cliente}"
    afectadas = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE clientes SET nombre=%s, nif=NULL, telefono=NULL, email=NULL, "
                        "direccion=NULL WHERE id=%s AND id_empresa=%s", (anon, id_cliente, id_empresa))
            afectadas += cur.rowcount
            cur.execute("UPDATE ventas SET cliente_nombre=%s, cliente_nif=NULL "
                        "WHERE id_empresa=%s AND cliente_id=%s", (anon, id_empresa, id_cliente))
            afectadas += cur.rowcount
            conn.commit()
    except Exception as e:
        logger.error("olvido: %s", e)
        sid = _registrar("olvido", "cliente", id_cliente, None, "error", None, solicitante, id_empresa)
        return {"ok": False, "solicitud": sid}
    sid = _registrar("olvido", "cliente", id_cliente, None, "resuelta", None, solicitante, id_empresa)
    return {"ok": True, "registros_anonimizados": afectadas, "solicitud": sid}


def listar_solicitudes(id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rgpd_solicitudes WHERE id_empresa=%s ORDER BY creado_en DESC", (id_empresa,))
            return [(r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r)))
                    for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_solicitudes: %s", e)
        return []


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("rgpd", accion, "rgpd_solicitudes", detalle)
    except Exception:
        pass
