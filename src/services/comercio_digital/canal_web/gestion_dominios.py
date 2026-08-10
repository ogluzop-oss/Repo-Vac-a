"""
Canal Web · Gestión de dominios (ops del Canal Web sobre dominios). Reutiliza los adaptadores de
registradores (`comercio_digital.dominios`, Adapter Pattern), `conexiones` (credenciales cifradas),
Event Bus, RBAC y auditoría. Persiste en `cd_canal_dominios` (multiempresa; clave por id_empresa, nunca
por dominio). El dominio activo se refleja en `cd_canal_web`. Aditivo, degradable. No es un motor nuevo.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from src.db.conexion import obtener_conexion

logger = logging.getLogger("cd.canal_web.dominios")

SUBDOMINIO_BASE = "smartmanager.ai"
_RE_DOMINIO = re.compile(r"^(?!-)[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63})+$", re.I)


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _e
    return _e(id_empresa)


def _puede(usuario, permiso, emp):
    perfil = (usuario or {}).get("perfil")
    if perfil in ("ADMINISTRADOR", "SUPERADMIN", "API"):
        return True
    try:
        from src.services import autorizacion
        return autorizacion.puede(usuario, permiso, id_empresa=emp)
    except Exception:
        return True


def _evento(tipo, emp, payload=None):
    try:
        from src.platform import capabilities as cap
        eb = cap.eventbus()
        if eb is not None:
            eb.publish(tipo, id_empresa=emp, ref_entidad="canal_web", ref_id=emp, payload=payload or {})
    except Exception as e:
        logger.debug("evento %s: %s", tipo, e)


def _audit(accion, emp, detalle=""):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("comercio_digital", f"CANAL_WEB_DOM_{accion}", "cd_canal_dominios",
                      f"empresa={emp} {detalle}"[:255])
    except Exception:
        pass


def _limpio(dominio) -> str:
    d = str(dominio or "").strip().lower()
    return re.sub(r"^https?://", "", d).strip("/").split("/")[0]


def validar_dominio(dominio) -> bool:
    return bool(_RE_DOMINIO.match(_limpio(dominio)))


def _slug(nombre) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(nombre or "tienda").lower()).strip("-")
    return s or "tienda"


# ── búsqueda / subdominio ─────────────────────────────────────────────────────
def buscar_dominios(nombre, *, id_empresa=None, usuario=None, proveedor=None) -> dict:
    emp = _emp(id_empresa)
    if not _puede(usuario, "canal_web.dominios.ver", emp):
        return {"ok": False, "error": "forbidden", "permiso": "canal_web.dominios.ver"}
    from src.services.comercio_digital import dominios as D
    ad = D.adaptador(proveedor)
    res = ad.buscar(nombre, contexto=D.contexto(emp, proveedor)) if ad else []
    _evento("CanalWebDominioBuscado", emp,
            {"nombre": nombre, "proveedor": getattr(ad, "codigo", None), "resultados": len(res)})
    _audit("BUSCAR", emp, f"nombre={nombre}")
    return {"ok": True, "proveedor": getattr(ad, "codigo", None), "resultados": res}


def _existe_dominio(dominio) -> bool:
    try:
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM cd_canal_dominios WHERE dominio=%s", (dominio,))
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0
    except Exception:
        return False


def generar_subdominio(nombre, *, id_empresa=None) -> str:
    """Genera un subdominio único slug.smartmanager.ai (slug-2, slug-3… si está ocupado)."""
    _emp(id_empresa)
    base = _slug(nombre)
    cand = f"{base}.{SUBDOMINIO_BASE}"
    i = 1
    while _existe_dominio(cand):
        i += 1
        cand = f"{base}-{i}.{SUBDOMINIO_BASE}"
    return cand


# ── persistencia / consulta ───────────────────────────────────────────────────
_COLS = ("id", "dominio", "tipo", "proveedor", "referencia", "precio", "moneda", "fecha_registro",
         "fecha_expiracion", "estado_dns", "estado_https", "renovacion_auto", "activo")


def listar_dominios(id_empresa=None) -> list:
    emp = _emp(id_empresa)
    out = []
    try:
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS)} FROM cd_canal_dominios WHERE id_empresa=%s "
                        "ORDER BY activo DESC, id DESC", (emp,))
            for r in cur.fetchall():
                out.append(r if isinstance(r, dict) else dict(zip(_COLS, r)))
    except Exception as e:
        logger.error("listar_dominios: %s", e)
    return out


def dominio_activo(id_empresa=None):
    for d in listar_dominios(id_empresa):
        if d.get("activo"):
            return d
    return None


def _set_estado(emp, dominio, **campos):
    if not campos:
        return
    sets = ", ".join(f"{k}=%s" for k in campos)
    try:
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(f"UPDATE cd_canal_dominios SET {sets} WHERE id_empresa=%s AND dominio=%s",
                        (*campos.values(), emp, dominio))
            c.commit()
    except Exception as e:
        logger.debug("_set_estado: %s", e)


def _sync_canal(emp, dom):
    try:
        from src.services.comercio_digital import canal_web
        canal_web._upsert(emp, dominio=dom,
                          endpoint=dom if dom.startswith(("http://", "https://")) else f"https://{dom}")
    except Exception as e:
        logger.debug("sync canal dominio: %s", e)


# ── DNS / HTTPS (preparado, degradable) ───────────────────────────────────────
def configurar_dns(dominio, *, id_empresa=None, proveedor=None) -> dict:
    emp = _emp(id_empresa)
    dom = _limpio(dominio)
    from src.services.comercio_digital import dominios as D
    ad = D.adaptador(proveedor)
    registros = [{"tipo": "A", "nombre": "@", "valor": "203.0.113.10"},
                 {"tipo": "CNAME", "nombre": "www", "valor": dom}]
    r = ad.configurar_dns(dom, registros, contexto=D.contexto(emp, proveedor)) if ad else {"ok": False}
    est = "configurado" if r.get("aplicado") else "manual"
    _set_estado(emp, dom, estado_dns=est)
    _evento("CanalWebDNSConfigurado", emp, {"dominio": dom, "estado": est})
    return {"ok": bool(r.get("ok")), "estado": est, "instrucciones": r.get("instrucciones")}


def activar_https(dominio, *, id_empresa=None, proveedor=None) -> dict:
    emp = _emp(id_empresa)
    dom = _limpio(dominio)
    from src.services.comercio_digital import dominios as D
    ad = D.adaptador(proveedor)
    r = ad.activar_https(dom, contexto=D.contexto(emp, proveedor)) if ad else {"ok": False}
    est = "activo" if r.get("aplicado") else "pendiente"
    _set_estado(emp, dom, estado_https=est)
    _evento("CanalWebHTTPSConfigurado", emp, {"dominio": dom, "estado": est})
    return {"ok": bool(r.get("ok")), "estado": est}


# ── asignación / compra / cambio / renovación ─────────────────────────────────
def asignar_dominio(dominio, *, tipo="propio", id_empresa=None, proveedor=None, referencia=None,
                    precio=None, fecha_expiracion=None, configurar=True) -> dict:
    """Registra/activa un dominio (activo=1, desactiva el resto), configura DNS+HTTPS (degradable) y
    sincroniza el dominio activo en `cd_canal_web`. Multiempresa (por id_empresa)."""
    emp = _emp(id_empresa)
    dom = _limpio(dominio)
    if not dom:
        return {"ok": False, "motivo": "dominio vacío"}
    try:
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE cd_canal_dominios SET activo=0 WHERE id_empresa=%s", (emp,))
            cur.execute(
                "INSERT INTO cd_canal_dominios (id_empresa,dominio,tipo,proveedor,referencia,precio,"
                "fecha_registro,fecha_expiracion,activo) VALUES (%s,%s,%s,%s,%s,%s,NOW(),%s,1) "
                "ON DUPLICATE KEY UPDATE tipo=VALUES(tipo),proveedor=VALUES(proveedor),"
                "referencia=VALUES(referencia),precio=VALUES(precio),"
                "fecha_expiracion=VALUES(fecha_expiracion),activo=1",
                (emp, dom, tipo, proveedor, referencia, precio, fecha_expiracion))
            c.commit()
    except Exception as e:
        logger.error("asignar_dominio: %s", e)
        return {"ok": False, "error": str(e)}
    _evento("CanalWebSubdominioCreado" if tipo == "subdominio" else "CanalWebDominioAsignado", emp,
            {"dominio": dom, "tipo": tipo})
    _audit("ASIGNAR", emp, f"dominio={dom} tipo={tipo}")
    dns = configurar_dns(dom, id_empresa=emp, proveedor=proveedor) if configurar else None
    https = activar_https(dom, id_empresa=emp, proveedor=proveedor) if configurar else None
    _sync_canal(emp, dom)
    return {"ok": True, "dominio": dom, "tipo": tipo, "dns": dns, "https": https}


def comprar_dominio(dominio, *, titular=None, id_empresa=None, usuario=None, proveedor=None) -> dict:
    emp = _emp(id_empresa)
    if not _puede(usuario, "canal_web.dominios.comprar", emp):
        return {"ok": False, "error": "forbidden", "permiso": "canal_web.dominios.comprar"}
    from src.services.comercio_digital import dominios as D
    ad = D.adaptador(proveedor)
    r = ad.comprar(_limpio(dominio), titular=titular or {}, contexto=D.contexto(emp, proveedor)) if ad \
        else {"ok": False}
    if not r.get("ok"):
        return {"ok": False, "motivo": r.get("error") or "no se pudo comprar"}
    _evento("CanalWebDominioComprado", emp,
            {"dominio": r.get("dominio"), "proveedor": ad.codigo, "precio": r.get("precio")})
    _audit("COMPRAR", emp, f"dominio={r.get('dominio')} ref={r.get('referencia')} precio={r.get('precio')}")
    asig = asignar_dominio(r.get("dominio"), tipo="comprado", id_empresa=emp, proveedor=ad.codigo,
                           referencia=r.get("referencia"), precio=r.get("precio"),
                           fecha_expiracion=r.get("fecha_expiracion"))
    return {"ok": True, "dominio": r.get("dominio"), "referencia": r.get("referencia"),
            "precio": r.get("precio"), "asignacion": asig}


def cambiar_dominio(dominio, *, id_empresa=None, usuario=None) -> dict:
    emp = _emp(id_empresa)
    if not _puede(usuario, "canal_web.dominios.administrar", emp):
        return {"ok": False, "error": "forbidden", "permiso": "canal_web.dominios.administrar"}
    dom = _limpio(dominio)
    if any(d.get("dominio") == dom for d in listar_dominios(emp)):
        try:
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("UPDATE cd_canal_dominios SET activo=0 WHERE id_empresa=%s", (emp,))
                cur.execute("UPDATE cd_canal_dominios SET activo=1 WHERE id_empresa=%s AND dominio=%s",
                            (emp, dom))
                c.commit()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        _sync_canal(emp, dom)
        _evento("CanalWebDominioAsignado", emp, {"dominio": dom})
        return {"ok": True, "dominio": dom}
    return asignar_dominio(dom, tipo="propio", id_empresa=emp)


def renovar_dominio(dominio, *, id_empresa=None, usuario=None, proveedor=None) -> dict:
    emp = _emp(id_empresa)
    if not _puede(usuario, "canal_web.dominios.renovar", emp):
        return {"ok": False, "error": "forbidden", "permiso": "canal_web.dominios.renovar"}
    from src.services.comercio_digital import dominios as D
    ad = D.adaptador(proveedor)
    r = ad.renovar(_limpio(dominio), contexto=D.contexto(emp, proveedor)) if ad else {"ok": False}
    if r.get("ok") and r.get("fecha_expiracion"):
        _set_estado(emp, _limpio(dominio), fecha_expiracion=r.get("fecha_expiracion"))
    _audit("RENOVAR", emp, f"dominio={_limpio(dominio)}")
    return {"ok": bool(r.get("ok")), "fecha_expiracion": r.get("fecha_expiracion")}


def metricas_dominios(id_empresa=None) -> dict:
    doms = listar_dominios(id_empresa)
    return {"total": len(doms),
            "dominios": len([d for d in doms if d.get("tipo") != "subdominio"]),
            "subdominios": len([d for d in doms if d.get("tipo") == "subdominio"]),
            "comprados": len([d for d in doms if d.get("tipo") == "comprado"]),
            "errores_dns": len([d for d in doms if d.get("estado_dns") == "error"]),
            "errores_https": len([d for d in doms if d.get("estado_https") == "error"])}


__all__ = ["SUBDOMINIO_BASE", "validar_dominio", "buscar_dominios", "generar_subdominio",
           "listar_dominios", "dominio_activo", "configurar_dns", "activar_https", "asignar_dominio",
           "comprar_dominio", "cambiar_dominio", "renovar_dominio", "metricas_dominios"]
