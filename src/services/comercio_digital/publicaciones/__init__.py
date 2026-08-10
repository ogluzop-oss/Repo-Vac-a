"""
PCD · Product Publication Layer (PPL) — CD-001/002/004 · Fase 7.

Única responsable de REPRESENTAR comercialmente un producto del ERP hacia cualquier canal. La
publicación NO es el producto:  Producto ERP → Product Publication Layer → Canal  (nunca Producto →
Canal). Construye la representación comercial reutilizable; NO modifica producto/inventario/precios/
dominio.

Invariantes (ratificadas):
  · Versionado INMUTABLE: nunca se sobrescribe una versión; toda modificación crea una versión nueva;
    las anteriores siguen recuperables; rollback = versión nueva (nunca destructivo).
  · Objetivo comercial y estado por publicación (solo arquitectura; la EJECUCIÓN de estados es de
    Workflow — no hay motor de estados paralelo).
  · Media SIEMPRE por referencia (Storage/CDN/Centro Documental); nunca almacena ficheros.
  · SEO e i18n (multi-idioma/región sin duplicar) preparados; sin generación automática (la IA solo
    PROPONE contenido en fases posteriores; nunca publica).
  · Los adaptadores RECIBEN una publicación ya preparada; la PPL nunca los invoca.
  · Reutiliza por CAPACIDADES: Event Bus (PublicationCreated/Updated/VersionCreated/Published/
    Archived/Rollback) y Observabilidad (Correlation ID / Communication ID / versión / objetivo /
    estado). No mueve stock, no reserva, no sincroniza, no usa IA, no publica en canales reales.
"""

from __future__ import annotations

import json
import logging
import uuid

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.comercio_digital.publicaciones import modelo  # noqa: F401
from src.services.comercio_digital.publicaciones.modelo import (  # noqa: F401
    ESTADOS, OBJETIVOS, ORIGENES, TIPOS, media_ref,
)

logger = logging.getLogger("cd.publicaciones")

FASE = 7


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
def _correlation_id() -> str:
    from src.services.comercio_digital import _base
    return _base.correlation_id("cdpub")


def _publicar(tipo, *, id_empresa=None, ref_id=None, payload=None):
    from src.services.comercio_digital import _base
    _base.publicar_evento(tipo, id_empresa=id_empresa, origen="comercio_digital.publicaciones",
                          ref_entidad="cd_publicacion", ref_id=ref_id, payload=payload)


def _dump(v):
    return json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else v


def _load(v, defecto=None):
    if v is None:
        return defecto
    try:
        return json.loads(v) if isinstance(v, str) else v
    except Exception:
        return defecto


def _fila(cur, cols):
    r = cur.fetchone()
    if r is None:
        return None
    vals = list(r.values()) if isinstance(r, dict) else list(r)
    return dict(zip(cols, vals))


def _semilla_producto(codigo, emp) -> dict:
    """Semilla de BORRADOR a partir del producto ERP (SOLO LECTURA; no modifica nada). El precio se
    copia como precio de escaparate (snapshot), nunca como precio interno."""
    out = {}
    if not codigo:
        return out
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT nombre, COALESCE(precio,0) FROM articulos WHERE codigo=%s AND "
                        "id_empresa=%s", (codigo, emp))
            f = _fila(cur, ("nombre", "precio"))
            if f:
                out = {"nombre": f["nombre"] or "", "precio_escaparate": float(f["precio"] or 0)}
    except Exception as e:
        logger.debug("semilla producto %s: %s", codigo, e)
    return out


# ── Publicaciones / versiones ─────────────────────────────────────────────────
def crear_publicacion(codigo_articulo=None, *, tipo="producto", objetivo=None, contenido=None,
                      seo=None, media=None, id_empresa=None, actor=None, origen="manual",
                      communication_id=None, sembrar=False):
    """Crea una publicación (versión 1, estado BORRADOR). No modifica el producto ERP."""
    emp = _emp(id_empresa)
    # Límite SaaS (Fase 9): cuota de publicaciones por plan/tenant. Degradable → permitido (sin
    # regresión). Reutiliza la gobernanza transversal (capacidad SaaS), nunca importa SaaS directo.
    try:
        from src.services.comercio_digital import gobernanza
        gobernanza.metrica("commerce_publicacion_crear")
        if not gobernanza.dentro_de_limite("cd_publicaciones", id_empresa=emp):
            logger.warning("límite SaaS de publicaciones alcanzado (empresa=%s)", emp)
            return None
    except Exception:
        pass
    if contenido is None and sembrar:
        contenido = _semilla_producto(codigo_articulo, emp)
    contenido, seo, media = contenido or {}, seo or {}, media or []
    id_pub = str(uuid.uuid4())
    cid = _correlation_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cd_publicaciones (id_publicacion, id_empresa, codigo_articulo, tipo, "
                "objetivo, estado, version_actual, usuario) VALUES (%s,%s,%s,%s,%s,'BORRADOR',1,%s)",
                (id_pub, emp, codigo_articulo, tipo, objetivo, actor))
            cur.execute(
                "INSERT INTO cd_publicacion_versiones (id_publicacion, id_empresa, version, estado, "
                "objetivo, contenido, seo, media, origen, correlation_id, communication_id, actor) "
                "VALUES (%s,%s,1,'BORRADOR',%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_pub, emp, objetivo, _dump(contenido), _dump(seo), _dump(media), origen, cid,
                 communication_id, actor))
            conn.commit()
    except Exception as e:
        logger.error("crear_publicacion: %s", e)
        return None
    _publicar("PublicationCreated", id_empresa=emp, ref_id=id_pub,
              payload={"tipo": tipo, "objetivo": objetivo, "version": 1, "correlation_id": cid})
    _publicar("PublicationVersionCreated", id_empresa=emp, ref_id=id_pub,
              payload={"version": 1, "origen": origen, "correlation_id": cid})
    return id_pub


_H_COLS = ("id_publicacion", "id_empresa", "codigo_articulo", "tipo", "objetivo", "estado",
           "version_actual", "ts_creado", "ts_actualizado")


def obtener(id_pub, id_empresa=None):
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_publicacion, id_empresa, codigo_articulo, tipo, objetivo, estado, "
                        "version_actual, ts_creado, ts_actualizado FROM cd_publicaciones WHERE "
                        "id_publicacion=%s AND id_empresa=%s", (id_pub, emp))
            return _fila(cur, _H_COLS)
    except Exception as e:
        logger.error("obtener(%s): %s", id_pub, e)
        return None


def listar(id_empresa=None, *, codigo_articulo=None, estado=None, tipo=None):
    emp = _emp(id_empresa)
    out = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = ("SELECT id_publicacion, id_empresa, codigo_articulo, tipo, objetivo, estado, "
                   "version_actual, ts_creado, ts_actualizado FROM cd_publicaciones WHERE id_empresa=%s")
            params = [emp]
            for campo, val in (("codigo_articulo", codigo_articulo), ("estado", estado),
                               ("tipo", tipo)):
                if val is not None:
                    sql += f" AND {campo}=%s"
                    params.append(val)
            sql += " ORDER BY ts_creado DESC"
            cur.execute(sql, tuple(params))
            for f in cur.fetchall():
                vals = list(f.values()) if isinstance(f, dict) else list(f)
                out.append(dict(zip(_H_COLS, vals)))
    except Exception as e:
        logger.error("listar: %s", e)
    return out


_V_COLS = ("version", "estado", "objetivo", "contenido", "seo", "media", "origen", "correlation_id",
           "communication_id", "actor", "ts_creado")


def obtener_version(id_pub, version=None, id_empresa=None):
    """Versión concreta (o la actual si version=None). Contenido/seo/media deserializados."""
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if version is None:
                cur.execute("SELECT version_actual FROM cd_publicaciones WHERE id_publicacion=%s AND "
                            "id_empresa=%s", (id_pub, emp))
                r = cur.fetchone()
                if not r:
                    return None
                version = list(r.values())[0] if isinstance(r, dict) else r[0]
            cur.execute("SELECT version, estado, objetivo, contenido, seo, media, origen, "
                        "correlation_id, communication_id, actor, ts_creado FROM "
                        "cd_publicacion_versiones WHERE id_publicacion=%s AND id_empresa=%s AND "
                        "version=%s", (id_pub, emp, version))
            f = _fila(cur, _V_COLS)
            if f:
                f["contenido"] = _load(f["contenido"], {})
                f["seo"] = _load(f["seo"], {})
                f["media"] = _load(f["media"], [])
            return f
    except Exception as e:
        logger.error("obtener_version(%s,%s): %s", id_pub, version, e)
        return None


def versiones(id_pub, id_empresa=None):
    emp = _emp(id_empresa)
    out = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT version, estado, objetivo, origen, ts_creado FROM "
                        "cd_publicacion_versiones WHERE id_publicacion=%s AND id_empresa=%s "
                        "ORDER BY version", (id_pub, emp))
            cols = ("version", "estado", "objetivo", "origen", "ts_creado")
            for f in cur.fetchall():
                vals = list(f.values()) if isinstance(f, dict) else list(f)
                out.append(dict(zip(cols, vals)))
    except Exception as e:
        logger.error("versiones(%s): %s", id_pub, e)
    return out


def nueva_version(id_pub, *, contenido=None, seo=None, media=None, objetivo=None, id_empresa=None,
                  actor=None, origen="manual", communication_id=None):
    """Crea una versión NUEVA (inmutable). Los campos no aportados se heredan de la versión actual.
    Nunca sobrescribe la anterior."""
    emp = _emp(id_empresa)
    prev = obtener_version(id_pub, None, emp)
    if prev is None:
        return None
    nueva = int(prev["version"]) + 1
    contenido = prev["contenido"] if contenido is None else contenido
    seo = prev["seo"] if seo is None else seo
    media = prev["media"] if media is None else media
    objetivo = prev["objetivo"] if objetivo is None else objetivo
    cid = _correlation_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cd_publicacion_versiones (id_publicacion, id_empresa, version, estado, "
                "objetivo, contenido, seo, media, origen, correlation_id, communication_id, actor) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_pub, emp, nueva, prev["estado"], objetivo, _dump(contenido), _dump(seo),
                 _dump(media), origen, cid, communication_id, actor))
            cur.execute("UPDATE cd_publicaciones SET version_actual=%s, objetivo=%s, "
                        "ts_actualizado=NOW() WHERE id_publicacion=%s AND id_empresa=%s",
                        (nueva, objetivo, id_pub, emp))
            conn.commit()
    except Exception as e:
        logger.error("nueva_version(%s): %s", id_pub, e)
        return None
    _publicar("PublicationVersionCreated", id_empresa=emp, ref_id=id_pub,
              payload={"version": nueva, "origen": origen, "correlation_id": cid})
    _publicar("PublicationUpdated", id_empresa=emp, ref_id=id_pub,
              payload={"version": nueva, "correlation_id": cid})
    return nueva


def rollback(id_pub, version_objetivo, *, id_empresa=None, actor=None):
    """Rollback NO destructivo: crea una versión nueva clonando el contenido de `version_objetivo`.
    Las versiones intermedias permanecen recuperables."""
    emp = _emp(id_empresa)
    objetivo_v = obtener_version(id_pub, version_objetivo, emp)
    if objetivo_v is None:
        return None
    nueva = nueva_version(id_pub, contenido=objetivo_v["contenido"], seo=objetivo_v["seo"],
                          media=objetivo_v["media"], objetivo=objetivo_v["objetivo"], id_empresa=emp,
                          actor=actor, origen="manual")
    if nueva:
        _publicar("PublicationRollback", id_empresa=emp, ref_id=id_pub,
                  payload={"desde_version": version_objetivo, "nueva_version": nueva})
    return nueva


def marcar_estado(id_pub, estado, *, id_empresa=None, actor=None, communication_id=None):
    """Persiste el estado de la publicación y emite el evento. La EJECUCIÓN/gobierno de la transición
    corresponde a Workflow (esta capa NO implementa un motor de estados)."""
    if estado not in ESTADOS:
        return False
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cd_publicaciones SET estado=%s, ts_actualizado=NOW() WHERE "
                        "id_publicacion=%s AND id_empresa=%s", (estado, id_pub, emp))
            if cur.rowcount == 0:
                return False
            conn.commit()
    except Exception as e:
        logger.error("marcar_estado(%s,%s): %s", id_pub, estado, e)
        return False
    _publicar(modelo.EVENTO_ESTADO.get(estado, "PublicationUpdated"), id_empresa=emp, ref_id=id_pub,
              payload={"estado": estado, "communication_id": communication_id})
    return True


# ── i18n (multi-idioma/región sin duplicar la publicación) ────────────────────
def set_i18n(id_pub, idioma, contenido, *, version=None, region="", id_empresa=None):
    """Registra/actualiza el contenido localizado de una versión para (idioma, region)."""
    emp = _emp(id_empresa)
    if version is None:
        h = obtener(id_pub, emp)
        if not h:
            return False
        version = h["version_actual"]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cd_publicacion_i18n (id_publicacion, version, id_empresa, idioma, "
                "region, contenido) VALUES (%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE contenido=VALUES(contenido)",
                (id_pub, version, emp, idioma, region or "", _dump(contenido)))
            conn.commit()
            return True
    except Exception as e:
        logger.error("set_i18n(%s,%s): %s", id_pub, idioma, e)
        return False


def obtener_i18n(id_pub, idioma, *, version=None, region="", id_empresa=None):
    emp = _emp(id_empresa)
    if version is None:
        h = obtener(id_pub, emp)
        if not h:
            return None
        version = h["version_actual"]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT contenido FROM cd_publicacion_i18n WHERE id_publicacion=%s AND "
                        "version=%s AND id_empresa=%s AND idioma=%s AND region=%s",
                        (id_pub, version, emp, idioma, region or ""))
            r = cur.fetchone()
            if not r:
                return None
            return _load(list(r.values())[0] if isinstance(r, dict) else r[0], {})
    except Exception as e:
        logger.error("obtener_i18n(%s,%s): %s", id_pub, idioma, e)
        return None


# ── Publicación preparada (la reciben los adaptadores; la PPL no los llama) ────
def preparar_para_canal(id_pub, *, idioma=None, region="", version=None, id_empresa=None):
    """Ensambla la representación comercial PREPARADA (contenido+seo+media, con overlay i18n) que un
    ADAPTADOR recibirá para traducir. La PPL NO invoca al adaptador ni publica en canal alguno."""
    emp = _emp(id_empresa)
    h = obtener(id_pub, emp)
    v = obtener_version(id_pub, version, emp)
    if not h or not v:
        return None
    prep = {"id_publicacion": id_pub, "tipo": h["tipo"], "objetivo": v["objetivo"],
            "estado": h["estado"], "version": v["version"], "codigo_articulo": h["codigo_articulo"],
            "contenido": dict(v["contenido"]), "seo": dict(v["seo"]), "media": list(v["media"]),
            "idioma": idioma, "region": region or ""}
    if idioma:
        loc = obtener_i18n(id_pub, idioma, version=v["version"], region=region, id_empresa=emp)
        if not loc and region:
            # Fallback de región: si no hay contenido para (idioma, region), usar (idioma, "").
            loc = obtener_i18n(id_pub, idioma, version=v["version"], region="", id_empresa=emp)
        if loc:
            prep["contenido"].update(loc.get("contenido", loc))
            if loc.get("seo"):
                prep["seo"].update(loc["seo"])
    return prep


def descriptor() -> dict:
    return {"servicio": "cd_publicaciones", "rfc": "CD-001/002/004", "fase": FASE,
            "estado": "implementado", "tipos": list(TIPOS), "objetivos": list(OBJETIVOS),
            "estados": list(ESTADOS), "versionado": "inmutable", "rollback": True,
            "media": "referencias (storage/cdn/documental)", "i18n": "multi-idioma/region sin duplicar",
            "seo": True, "estados_por": "workflow", "genera_ia": False, "publica_en_canal": False,
            "mueve_stock": False, "modifica_producto": False}


__all__ = ["FASE", "modelo", "media_ref", "crear_publicacion", "obtener", "listar", "obtener_version",
           "versiones", "nueva_version", "rollback", "marcar_estado", "set_i18n", "obtener_i18n",
           "preparar_para_canal", "descriptor"]
