"""
PCD · Automatización comercial (Etapa B · Fase B8 — cierre de la Etapa B).

Automatiza la operativa comercial REUTILIZANDO lo ya construido (no crea motores):
  · Feeds de producto → `catalogo` (Catálogo Comercial Global) + `sync` (encolar a canal).
  · Republicación → `presencia` (IA PROPONE contenido; nunca publica) + `sync`.
  · SEO/optimización → `presencia.proponer(tipos=('seo',))` (versión ia_propuesta; Workflow gobierna).
  · Campañas → definición programable (cd_campanas) despachada por `sync`/`presencia`.
  · Programación → Scheduler (capacidad); Análisis → Observabilidad/BI (capacidad, degradable).

Principios: IA provider-agnostic y SOLO propositiva (Workflow decide la publicación); la publicación a
canales pasa por el Sync Engine (Dominio→Adaptador→canal). Multiempresa. Degradable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("cd.automatizacion")

FASE = "B8"
TIPOS = ("feed", "republicacion", "seo", "campana")


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
# ── Feeds ─────────────────────────────────────────────────────────────────────
def generar_feed(id_empresa=None, *, canal=None, pais=None, idioma=None, moneda="EUR",
                 estado="PUBLICADA"):
    """Genera un feed de producto a partir del Catálogo Comercial Global (fichas compuestas)."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital import catalogo
    items = []
    for f in catalogo.catalogo(emp, pais=pais, idioma=idioma, moneda=moneda, estado=estado):
        cont = f.get("contenido") or {}
        media = f.get("media") or []
        items.append({"id": f["id_publicacion"], "titulo": cont.get("nombre"),
                      "descripcion": cont.get("descripcion"), "precio": f["precio"]["total"],
                      "moneda": f["moneda"], "imagen": (media[0] if media else None),
                      "seo": f.get("seo"), "canal": canal})
    return items


def publicar_feed(id_empresa=None, *, canal, pais=None, idioma=None, moneda="EUR"):
    """Genera el feed y lo ENCOLA en el Sync Engine para el canal (idempotente por publicación).
    No publica directamente: el adaptador del canal lo entrega."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital import sync
    feed = generar_feed(emp, canal=canal, pais=pais, idioma=idioma, moneda=moneda)
    encolados = 0
    for item in feed:
        if sync.encolar(canal, "catalogo.feed", item, id_empresa=emp,
                        idempotencia_key=f"feed:{canal}:{item['id']}"):
            encolados += 1
    return {"ok": True, "canal": canal, "items": len(feed), "encolados": encolados}


# ── Republicación / SEO (IA propone; Workflow gobierna) ───────────────────────
def optimizar_seo(id_publicacion, *, id_empresa=None, actor=None):
    """La IA PROPONE SEO (versión ia_propuesta en la PPL). No publica."""
    from src.services.comercio_digital import presencia
    return presencia.proponer(id_publicacion, tipos=("seo",), id_empresa=_emp(id_empresa),
                              actor=actor or "automatizacion")


def republicar(id_publicacion, *, canal=None, id_empresa=None, tipos=("descripcion", "seo"),
               actor=None):
    """Refresca el contenido (IA propone) y ENCOLA la publicación al canal (si se indica). La
    publicación real la gobierna Workflow; aquí solo se propone + encola."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital import presencia
    prop = presencia.proponer(id_publicacion, tipos=tipos, id_empresa=emp,
                              actor=actor or "automatizacion")
    encolado = None
    if canal and prop:
        from src.services.comercio_digital import catalogo, sync
        ficha = catalogo.ficha_comercial(id_publicacion, id_empresa=emp)
        encolado = sync.encolar(canal, "publicacion.push", ficha, id_empresa=emp,
                                idempotencia_key=f"republicar:{canal}:{id_publicacion}:{prop['version']}")
    return {"ok": bool(prop), "propuesta": prop, "encolado": bool(encolado), "canal": canal}


# ── Campañas (definición programable) ─────────────────────────────────────────
def crear_campana(nombre, *, tipo="feed", canal=None, objetivo=None, parametros=None,
                  programacion=None, id_empresa=None, actor=None):
    emp = _emp(id_empresa)
    if tipo not in TIPOS:
        tipo = "feed"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO cd_campanas (id_empresa, nombre, tipo, canal, objetivo, "
                        "parametros, programacion, actor) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, nombre, tipo, canal, objetivo, json.dumps(parametros or {}),
                         programacion, actor))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_campana(%s): %s", nombre, e)
        return None


def ejecutar_campana(id_campana, *, id_empresa=None):
    """Ejecuta una campaña según su tipo (feed/republicación/SEO) y registra el resultado."""
    emp = _emp(id_empresa)
    c = _campana(id_campana, emp)
    if not c:
        return {"ok": False, "motivo": "campaña no encontrada"}
    params = c.get("parametros") or {}
    tipo, canal = c.get("tipo"), c.get("canal")
    if tipo == "feed":
        res = publicar_feed(emp, canal=canal, pais=params.get("pais"), idioma=params.get("idioma"),
                            moneda=params.get("moneda", "EUR"))
    elif tipo in ("republicacion", "campana"):
        res = {"republicadas": [republicar(pid, canal=canal, id_empresa=emp)
                                for pid in (params.get("publicaciones") or [])]}
    elif tipo == "seo":
        res = {"optimizadas": [optimizar_seo(pid, id_empresa=emp)
                               for pid in (params.get("publicaciones") or [])]}
    else:
        res = {"ok": False, "motivo": "tipo no soportado"}
    _registrar_run(id_campana, res)
    return {"ok": True, "tipo": tipo, "resultado": res}


def programar(id_campana, *, id_empresa=None):
    """Programa la ejecución periódica en el Scheduler (capacidad, degradable/opt-in)."""
    emp = _emp(id_empresa)
    try:
        from src.platform import capabilities as cap
        sch = cap.scheduler()
        if sch is not None and hasattr(sch, "registrar_job"):
            sch.registrar_job(f"cd_campana_{id_campana}",
                              lambda *_a, **_k: ejecutar_campana(id_campana, id_empresa=emp))
            return True
    except Exception as e:
        logger.debug("programar campaña (%s): %s", id_campana, e)
    return False


def listar_campanas(id_empresa=None, *, estado=None):
    emp = _emp(id_empresa)
    out = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = ("SELECT id, nombre, tipo, canal, objetivo, estado, ultimo_run FROM cd_campanas "
                   "WHERE id_empresa=%s")
            params = [emp]
            if estado:
                sql += " AND estado=%s"
                params.append(estado)
            sql += " ORDER BY id DESC"
            cur.execute(sql, tuple(params))
            cols = ("id", "nombre", "tipo", "canal", "objetivo", "estado", "ultimo_run")
            for f in cur.fetchall():
                out.append(f if isinstance(f, dict) else dict(zip(cols, f)))
    except Exception as e:
        logger.error("listar_campanas: %s", e)
    return out


# ── Análisis (degradable) ─────────────────────────────────────────────────────
def analizar(id_empresa=None, *, canal=None):
    """Resumen comercial (degradable): nº de publicaciones publicadas y campañas activas. Un análisis
    IA más rico se apoyará en la capacidad de BI/Observabilidad cuando proceda."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital import publicaciones
    publicadas = len(publicaciones.listar(emp, estado="PUBLICADA"))
    campanas = len(listar_campanas(emp, estado="activa"))
    return {"publicaciones_publicadas": publicadas, "campanas_activas": campanas, "canal": canal}


# ── helpers ───────────────────────────────────────────────────────────────────
def _campana(id_campana, emp):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, nombre, tipo, canal, objetivo, parametros FROM cd_campanas "
                        "WHERE id=%s AND id_empresa=%s", (id_campana, emp))
            r = cur.fetchone()
            if not r:
                return None
            cols = ("id", "nombre", "tipo", "canal", "objetivo", "parametros")
            d = r if isinstance(r, dict) else dict(zip(cols, r))
            if isinstance(d.get("parametros"), str):
                try:
                    d["parametros"] = json.loads(d["parametros"])
                except Exception:
                    d["parametros"] = {}
            return d
    except Exception as e:
        logger.error("_campana(%s): %s", id_campana, e)
        return None


def _registrar_run(id_campana, resultado):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cd_campanas SET ultimo_run=%s, ultimo_resultado=%s, "
                        "ts_actualizado=%s WHERE id=%s",
                        (datetime.now(), json.dumps(resultado, ensure_ascii=False, default=str)[:60000],
                         datetime.now(), id_campana))
            conn.commit()
    except Exception as e:
        logger.error("_registrar_run(%s): %s", id_campana, e)


def descriptor() -> dict:
    return {"servicio": "cd_automatizacion", "etapa": "B", "fase": FASE, "estado": "implementado",
            "capacidades": ["feed", "republicacion", "seo", "campana", "programacion", "analisis"],
            "reutiliza": ["presencia", "catalogo", "sync", "scheduler", "observabilidad"],
            "ia_solo_propone": True, "publica_directo": False, "crea_motor_nuevo": False}


__all__ = ["FASE", "TIPOS", "generar_feed", "publicar_feed", "optimizar_seo", "republicar",
           "crear_campana", "ejecutar_campana", "programar", "listar_campanas", "analizar",
           "descriptor"]
