"""
PCD · Conexiones de canal (Etapa B · Fase B1). Registro seguro, por tenant, de las conexiones a
servicios externos (marketplaces, pasarelas, transportistas, canales propios) que consumirán los
conectores reales del Channel Adapter Framework.

Principios (Etapa A, invariantes):
  · Credenciales NUNCA en claro ni en código: se cifran con el secret manager Enterprise
    (`capabilities.secret_manager`) o se referencian por nombre de secreto externo (`secret_ref`).
  · Multiempresa/multitienda estricto; auditable (eventos por Event Bus); reversible.
  · No es un motor: es un registro que ALIMENTA a los adaptadores. La resolución de credenciales
    ocurre en runtime al construir el `AdapterContext`; nunca se persiste el secreto en claro.
  · Reutiliza SOLO `platform.capabilities` (secret_manager/eventbus). Ningún proveedor toca el dominio.
"""

from __future__ import annotations

import json
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.comercio_digital.canales.adaptador import AdapterContext

logger = logging.getLogger("cd.conexiones")

FASE = "B1"
TIPOS_AUTH = ("apikey", "oauth2", "basic", "hmac", "none")


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
def _cifrar(valor):
    """Cifra un secreto vía capacidad secret_manager. Si no está disponible, NO persiste en claro."""
    if valor is None:
        return None
    try:
        from src.platform import capabilities as cap
        sm = cap.secret_manager()
        if sm is not None and hasattr(sm, "cifrar"):
            return sm.cifrar(valor if isinstance(valor, str) else json.dumps(valor))
    except Exception as e:
        logger.error("cifrar credenciales: %s", e)
    return None      # sin secret manager → no se guarda el secreto (nunca en claro)


def _descifrar(token):
    if not token:
        return None
    try:
        from src.platform import capabilities as cap
        sm = cap.secret_manager()
        if sm is not None and hasattr(sm, "descifrar"):
            claro = sm.descifrar(token)
            try:
                return json.loads(claro)
            except Exception:
                return claro
    except Exception as e:
        logger.debug("descifrar credenciales: %s", e)
    return None


def _secreto_por_ref(ref):
    if not ref:
        return None
    try:
        from src.platform import capabilities as cap
        sm = cap.secret_manager()
        if sm is not None and hasattr(sm, "obtener_secreto"):
            return sm.obtener_secreto(ref)
    except Exception:
        pass
    return None


def _evento(tipo, id_empresa, canal, nombre):
    try:
        from src.platform import capabilities as cap
        bus = cap.eventbus()
        if bus is not None and hasattr(bus, "publish"):
            bus.publish(tipo, id_empresa=id_empresa, origen="comercio_digital.conexiones",
                        ref_entidad="cd_conexion", ref_id=f"{canal}:{nombre}",
                        payload={"canal": canal, "nombre": nombre})
    except Exception:
        pass


def registrar(canal, *, nombre="default", id_empresa=None, id_tienda=None, tipo_auth="apikey",
              endpoint_base=None, config=None, credenciales=None, secret_ref=None, actor=None):
    """Registra/actualiza una conexión. `credenciales` (dict/str) se CIFRA; nunca se guarda en claro.
    Alternativamente `secret_ref` apunta a un secreto externo. Devuelve True/False."""
    emp = _emp(id_empresa)
    if tipo_auth not in TIPOS_AUTH:
        tipo_auth = "apikey"
    cif = _cifrar(credenciales) if credenciales is not None else None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cd_conexiones (id_empresa, id_tienda, canal, nombre, tipo_auth, "
                "endpoint_base, config, credenciales_cifradas, secret_ref, actor) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE id_tienda=VALUES(id_tienda), tipo_auth=VALUES(tipo_auth), "
                "endpoint_base=VALUES(endpoint_base), config=VALUES(config), "
                "credenciales_cifradas=COALESCE(VALUES(credenciales_cifradas), credenciales_cifradas), "
                "secret_ref=VALUES(secret_ref), estado='ACTIVA', ts_actualizado=NOW()",
                (emp, id_tienda, canal, nombre, tipo_auth, endpoint_base,
                 json.dumps(config) if config else None, cif, secret_ref, actor))
            conn.commit()
        _evento("CommerceConnectionRegistered", emp, canal, nombre)
        return True
    except Exception as e:
        logger.error("registrar conexion (%s/%s): %s", canal, nombre, e)
        return False


_COLS = ("id", "id_empresa", "id_tienda", "canal", "nombre", "tipo_auth", "endpoint_base", "config",
         "secret_ref", "estado", "ultimo_test", "ultimo_resultado", "ts_creado")
_SEL = ("id, id_empresa, id_tienda, canal, nombre, tipo_auth, endpoint_base, config, secret_ref, "
        "estado, ultimo_test, ultimo_resultado, ts_creado")


def obtener(canal, *, nombre="default", id_empresa=None):
    """Config de una conexión SIN credenciales (nunca se devuelve el secreto)."""
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_SEL} FROM cd_conexiones WHERE id_empresa=%s AND canal=%s AND "
                        "nombre=%s", (emp, canal, nombre))
            r = cur.fetchone()
            if not r:
                return None
            d = r if isinstance(r, dict) else dict(zip(_COLS, r))
            if isinstance(d.get("config"), str):
                try:
                    d["config"] = json.loads(d["config"])
                except Exception:
                    pass
            return d
    except Exception as e:
        logger.error("obtener conexion (%s): %s", canal, e)
        return None


def listar(id_empresa=None, *, canal=None):
    emp = _emp(id_empresa)
    out = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = f"SELECT {_SEL} FROM cd_conexiones WHERE id_empresa=%s"
            params = [emp]
            if canal:
                sql += " AND canal=%s"
                params.append(canal)
            sql += " ORDER BY canal, nombre"
            cur.execute(sql, tuple(params))
            for r in cur.fetchall():
                out.append(r if isinstance(r, dict) else dict(zip(_COLS, r)))
    except Exception as e:
        logger.error("listar conexiones: %s", e)
    return out


def eliminar(canal, *, nombre="default", id_empresa=None):
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cd_conexiones WHERE id_empresa=%s AND canal=%s AND nombre=%s",
                        (emp, canal, nombre))
            conn.commit()
            ok = cur.rowcount > 0
        if ok:
            _evento("CommerceConnectionRemoved", emp, canal, nombre)
        return ok
    except Exception as e:
        logger.error("eliminar conexion (%s): %s", canal, e)
        return False


def credenciales(canal, *, nombre="default", id_empresa=None):
    """Resuelve las credenciales en RUNTIME (descifra + secreto externo). Uso interno del transporte;
    NUNCA se persiste el resultado ni se registra en claro."""
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT credenciales_cifradas, secret_ref FROM cd_conexiones WHERE "
                        "id_empresa=%s AND canal=%s AND nombre=%s", (emp, canal, nombre))
            r = cur.fetchone()
        if not r:
            return {}
        cif, ref = (r["credenciales_cifradas"], r["secret_ref"]) if isinstance(r, dict) else (r[0], r[1])
        cred = _descifrar(cif) or {}
        if not isinstance(cred, dict):
            cred = {"secreto": cred}
        val_ref = _secreto_por_ref(ref)
        if val_ref:
            cred = {**cred, "secret_ref_valor": val_ref}
        return cred
    except Exception as e:
        logger.error("credenciales(%s): %s", canal, e)
        return {}


def contexto(canal, *, nombre="default", id_empresa=None, correlation_id=None):
    """Construye el `AdapterContext` que recibe un conector real: config + credenciales resueltas en
    runtime. Degradable: si no hay conexión, devuelve un contexto vacío (mismo comportamiento previo)."""
    emp = _emp(id_empresa)
    conf = obtener(canal, nombre=nombre, id_empresa=emp)
    cred = credenciales(canal, nombre=nombre, id_empresa=emp) if conf else {}
    extra = {"endpoint_base": (conf or {}).get("endpoint_base"), "tipo_auth": (conf or {}).get("tipo_auth"),
             "config": (conf or {}).get("config") or {}, "nombre": nombre} if conf else {}
    return AdapterContext(id_empresa=emp, canal=canal, correlation_id=correlation_id,
                          credenciales=cred, extra=extra)


def probar(canal, *, nombre="default", id_empresa=None):
    """Prueba de conexión DEGRADABLE (no realiza llamadas en vivo por defecto): valida que exista
    configuración y credenciales resolubles. Registra el resultado. Devuelve dict {ok, motivo}."""
    emp = _emp(id_empresa)
    conf = obtener(canal, nombre=nombre, id_empresa=emp)
    if not conf:
        return {"ok": False, "motivo": "conexión no encontrada"}
    tiene_cred = bool(credenciales(canal, nombre=nombre, id_empresa=emp)) or conf.get("tipo_auth") == "none"
    ok = bool(conf.get("endpoint_base")) and tiene_cred
    motivo = "config y credenciales presentes" if ok else "falta endpoint o credenciales"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cd_conexiones SET ultimo_test=NOW(), ultimo_resultado=%s, "
                        "estado=%s WHERE id_empresa=%s AND canal=%s AND nombre=%s",
                        (motivo[:255], "ACTIVA" if ok else "ERROR", emp, canal, nombre))
            conn.commit()
    except Exception:
        pass
    return {"ok": ok, "motivo": motivo}


def descriptor() -> dict:
    return {"servicio": "cd_conexiones", "etapa": "B", "fase": FASE, "estado": "implementado",
            "tipos_auth": list(TIPOS_AUTH), "credenciales": "cifradas (secret_manager) / secret_ref",
            "secretos_en_claro": False, "multiempresa": True, "multitienda": True,
            "reutiliza": ["secret_manager", "eventbus"], "es_motor": False}


__all__ = ["FASE", "TIPOS_AUTH", "registrar", "obtener", "listar", "eliminar", "credenciales",
           "contexto", "probar", "descriptor"]
