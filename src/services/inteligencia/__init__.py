"""
Etapa C · Centro de Decisiones Empresariales (capa TRANSVERSAL de inteligencia).

NO es una IA paralela ni un asistente nuevo: UNIFICA la capa de IA existente (`src.services.ia`:
recomendaciones/anomalías/riesgos/predicciones) en un LEDGER de decisiones PROPUESTAS, auditable
(Decision/Audit Replay), con aceptación/rechazo/feedback supervisado. Reutiliza RBAC (autorización),
Event Bus (auditoría) y Observabilidad (correlation) por capacidades.

Invariantes: nunca modifica datos (solo propone); la ejecución sigue siendo de Workflow + decisión
humana; toda decisión queda registrada y reconstruible; multiempresa; degradable.
"""

from __future__ import annotations

import json
import logging
import uuid

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("inteligencia")

FASE = "C1"

# Registro de proveedores de decisiones (transversal, pluggable). nombre → (callable, tipo).
_PROVEEDORES: dict = {}

# Mapa entidad → dominio (para clasificar las decisiones por área de negocio).
_DOMINIO = {"articulo": "inventario", "rotura_stock": "inventario", "exceso_stock": "inventario",
            "facturacion": "ventas", "impago": "tesoreria", "rrhh": "rrhh",
            "sincronizacion": "infraestructura", "prediccion": "prediccion"}
_PRIO = {"ALTA": "ALTA", "CRITICO": "ALTA", "CRITICA": "ALTA", "ALTA_": "ALTA", "alta": "ALTA",
         "critico": "ALTA", "critica": "ALTA", "MEDIA": "MEDIA", "media": "MEDIA",
         "BAJA": "BAJA", "baja": "BAJA", "INFO": "INFO", "info": "INFO"}


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _puede(usuario, permiso, id_empresa):
    """RBAC por capacidad (degradable/legacy-safe)."""
    try:
        from src.platform import capabilities as cap
        rbac = cap.rbac()
        if rbac is not None and hasattr(rbac, "puede"):
            return bool(rbac.puede(usuario, permiso, id_empresa=id_empresa))
    except Exception:
        pass
    return True


def _correlation():
    try:
        from src.platform import capabilities as cap
        obs = cap.observabilidad()
        corr = getattr(obs, "correlation", None)
        if corr is None and obs is not None:
            import importlib
            corr = importlib.import_module("src.services.observabilidad.correlation")
        if corr is not None and hasattr(corr, "nuevo"):
            return corr.nuevo("decision")
    except Exception:
        pass
    return "decision-" + uuid.uuid4().hex[:12]


def _evento(tipo, id_empresa, ref_id, payload):
    try:
        from src.platform import capabilities as cap
        bus = cap.eventbus()
        if bus is not None and hasattr(bus, "publish"):
            bus.publish(tipo, id_empresa=id_empresa, origen="inteligencia",
                        ref_entidad="decision_ia", ref_id=ref_id, payload=payload)
    except Exception as e:
        logger.debug("event bus (%s): %s", tipo, e)


# ── Proveedores (reutilizan la capa IA existente; NO se reimplementa nada) ────
def registrar_proveedor(nombre, fn, *, tipo="recomendacion"):
    _PROVEEDORES[nombre] = (fn, tipo)
    return nombre


def _proveedores_por_defecto():
    """Registra (idempotente) los generadores de la capa IA existente como proveedores."""
    if "ia.recomendaciones" in _PROVEEDORES:
        return
    try:
        from src.services.ia import anomalias, predicciones, recomendaciones, riesgos
        registrar_proveedor("ia.recomendaciones", recomendaciones.generar, tipo="recomendacion")
        registrar_proveedor("ia.anomalias", anomalias.detectar, tipo="anomalia")
        registrar_proveedor("ia.riesgos", riesgos.evaluar, tipo="riesgo")
        registrar_proveedor("ia.predicciones", predicciones.predecir, tipo="prediccion")
    except Exception as e:
        logger.debug("proveedores por defecto: %s", e)


def _prio(valor):
    return _PRIO.get(str(valor), "MEDIA" if valor else "BAJA")


def _normalizar(item, tipo, origen):
    d = item.to_dict() if hasattr(item, "to_dict") else (item if isinstance(item, dict) else {})
    conf = None
    if tipo == "recomendacion":
        titulo, desc = d.get("accion"), d.get("motivo")
        entidad, ref, prio, wf = d.get("entidad"), d.get("entidad_id"), d.get("prioridad"), d.get("workflow")
    elif tipo == "anomalia":
        titulo, desc = d.get("tipo"), d.get("descripcion")
        entidad, ref, prio, wf = d.get("tipo"), "", d.get("severidad"), None
    elif tipo == "riesgo":
        titulo, desc = d.get("tipo"), d.get("descripcion")
        entidad, ref, prio, wf, conf = d.get("entidad"), d.get("entidad_id"), d.get("nivel"), None, d.get("score")
    else:  # prediccion
        titulo, desc = d.get("metrica"), d.get("detalle")
        entidad, ref, prio, wf, conf = "prediccion", d.get("metrica"), "INFO", None, d.get("confianza")
    dominio = _DOMINIO.get(str(entidad), None) or _DOMINIO.get(str(titulo), None) or (entidad or "general")
    clave = f"{origen}:{ref or ''}:{titulo or ''}"[:200]
    return {"tipo": tipo, "origen": origen, "titulo": (titulo or "")[:160],
            "descripcion": (desc or "")[:500], "entidad": (str(entidad) if entidad else "")[:40],
            "entidad_ref": (str(ref) if ref else "")[:80], "prioridad": _prio(prio),
            "workflow": wf, "confianza": conf, "dominio": str(dominio)[:40], "datos": d, "clave": clave}


def _existe_abierta(cur, emp, clave):
    cur.execute("SELECT 1 FROM decisiones_ia WHERE id_empresa=%s AND clave=%s AND estado='propuesta' "
                "LIMIT 1", (emp, clave))
    return cur.fetchone() is not None


def generar(id_empresa=None, *, proveedores=None, actor="sistema"):
    """Ejecuta los proveedores (capa IA existente) y REGISTRA las decisiones propuestas (deduplicando
    las ya abiertas). Audita el evento. No modifica datos de negocio."""
    _proveedores_por_defecto()
    emp = _emp(id_empresa)
    cid = _correlation()
    provs = {k: _PROVEEDORES[k] for k in (proveedores or _PROVEEDORES) if k in _PROVEEDORES}
    creadas = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for nombre, (fn, tipo) in provs.items():
                try:
                    items = fn(emp) or []
                except Exception as e:
                    logger.debug("proveedor %s: %s", nombre, e)
                    continue
                for it in items:
                    d = _normalizar(it, tipo, nombre)
                    if _existe_abierta(cur, emp, d["clave"]):
                        continue
                    cur.execute(
                        "INSERT INTO decisiones_ia (id_empresa, dominio, tipo, origen, titulo, "
                        "descripcion, entidad, entidad_ref, prioridad, workflow_sugerido, confianza, "
                        "datos, clave, correlation_id, actor) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, d["dominio"], d["tipo"], d["origen"], d["titulo"], d["descripcion"],
                         d["entidad"], d["entidad_ref"], d["prioridad"], d["workflow"], d["confianza"],
                         json.dumps(d["datos"], ensure_ascii=False, default=str), d["clave"], cid, actor))
                    creadas += 1
            conn.commit()
    except Exception as e:
        logger.error("generar decisiones: %s", e)
    _evento("DecisionsGenerated", emp, None, {"creadas": creadas, "correlation_id": cid})
    return {"ok": True, "generadas": creadas, "correlation_id": cid}


def proponer(dominio, tipo, titulo, descripcion, *, entidad=None, entidad_ref=None, prioridad="MEDIA",
             workflow=None, datos=None, confianza=None, origen="automatizacion", id_empresa=None,
             actor="sistema"):
    """Registra UNA decisión propuesta ad-hoc (p. ej. desde una automatización). Deduplica propuestas
    abiertas por clave. Audita el evento. NO modifica datos de negocio. Devuelve el id o None."""
    emp = _emp(id_empresa)
    cid = _correlation()
    clave = f"{origen}:{entidad_ref or ''}:{titulo or ''}"[:200]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if _existe_abierta(cur, emp, clave):
                return None
            cur.execute(
                "INSERT INTO decisiones_ia (id_empresa, dominio, tipo, origen, titulo, descripcion, "
                "entidad, entidad_ref, prioridad, workflow_sugerido, confianza, datos, clave, "
                "correlation_id, actor) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (emp, str(dominio)[:40], tipo, origen, (titulo or "")[:160], (descripcion or "")[:500],
                 (str(entidad) if entidad else "")[:40], (str(entidad_ref) if entidad_ref else "")[:80],
                 _prio(prioridad), workflow, confianza,
                 json.dumps(datos or {}, ensure_ascii=False, default=str), clave, cid, actor))
            conn.commit()
            did = cur.lastrowid
    except Exception as e:
        logger.error("proponer(%s): %s", titulo, e)
        return None
    _evento("DecisionProposed", emp, did, {"origen": origen, "prioridad": _prio(prioridad),
                                           "workflow": workflow, "correlation_id": cid})
    return did


_COLS = ("id", "dominio", "tipo", "origen", "titulo", "descripcion", "entidad", "entidad_ref",
         "prioridad", "workflow_sugerido", "confianza", "estado", "feedback", "ts_creado")
_SEL = ("id, dominio, tipo, origen, titulo, descripcion, entidad, entidad_ref, prioridad, "
        "workflow_sugerido, confianza, estado, feedback, ts_creado")
_ORDEN = "FIELD(prioridad,'ALTA','MEDIA','BAJA','INFO'), id DESC"


def decisiones(id_empresa=None, *, dominio=None, tipo=None, estado="propuesta", prioridad=None,
               usuario=None, limite=200):
    """Decisiones propuestas (RBAC: `inteligencia.ver`). Ordenadas por prioridad."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "inteligencia.ver", emp):
        return []
    out = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = f"SELECT {_SEL} FROM decisiones_ia WHERE id_empresa=%s"
            params = [emp]
            for campo, val in (("estado", estado), ("dominio", dominio), ("tipo", tipo),
                               ("prioridad", prioridad)):
                if val is not None:
                    sql += f" AND {campo}=%s"
                    params.append(val)
            sql += f" ORDER BY {_ORDEN} LIMIT %s"
            params.append(int(limite))
            cur.execute(sql, tuple(params))
            for f in cur.fetchall():
                out.append(f if isinstance(f, dict) else dict(zip(_COLS, f)))
    except Exception as e:
        logger.error("decisiones: %s", e)
    return out


def obtener(id_decision, *, id_empresa=None, usuario=None):
    """Una decisión con su justificación auditable (`datos`)."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "inteligencia.ver", emp):
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {_SEL}, datos, correlation_id FROM decisiones_ia WHERE id=%s AND "
                        "id_empresa=%s", (id_decision, emp))
            r = cur.fetchone()
            if not r:
                return None
            cols = _COLS + ("datos", "correlation_id")
            d = r if isinstance(r, dict) else dict(zip(cols, r))
            if isinstance(d.get("datos"), str):
                try:
                    d["datos"] = json.loads(d["datos"])
                except Exception:
                    pass
            return d
    except Exception as e:
        logger.error("obtener(%s): %s", id_decision, e)
        return None


def resumen(id_empresa=None, *, usuario=None):
    """Resumen ejecutivo (semilla del Panel Ejecutivo): recuento por prioridad y dominio."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "inteligencia.ver", emp):
        return {}
    res = {"por_prioridad": {}, "por_dominio": {}, "por_tipo": {}, "total": 0}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for campo in ("prioridad", "dominio", "tipo"):
                cur.execute(f"SELECT {campo}, COUNT(*) FROM decisiones_ia WHERE id_empresa=%s AND "
                            f"estado='propuesta' GROUP BY {campo}", (emp,))
                mapa = {}
                for f in cur.fetchall():
                    vals = list(f.values()) if isinstance(f, dict) else list(f)
                    mapa[vals[0]] = int(vals[1])
                res[{"prioridad": "por_prioridad", "dominio": "por_dominio", "tipo": "por_tipo"}[campo]] = mapa
            res["total"] = sum(res["por_prioridad"].values())
    except Exception as e:
        logger.error("resumen: %s", e)
    return res


def _resolver(id_decision, emp, estado, *, feedback=None, actor=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE decisiones_ia SET estado=%s, feedback=COALESCE(%s, feedback), "
                        "actor=%s, ts_resuelto=NOW() WHERE id=%s AND id_empresa=%s AND "
                        "estado='propuesta'", (estado, feedback, actor, id_decision, emp))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("_resolver(%s,%s): %s", id_decision, estado, e)
        return False


def aceptar(id_decision, *, usuario=None, id_empresa=None):
    """Marca la decisión ACEPTADA (auditable). NO ejecuta ni modifica datos: la ejecución es de
    Workflow + decisión humana. RBAC: `inteligencia.decidir`."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "inteligencia.decidir", emp):
        return {"ok": False, "motivo": "no autorizado"}
    ok = _resolver(id_decision, emp, "aceptada", actor=_actor(usuario))
    if ok:
        _evento("DecisionAccepted", emp, id_decision, {"usuario": _actor(usuario)})
    return {"ok": ok}


def rechazar(id_decision, *, motivo=None, usuario=None, id_empresa=None):
    emp = _emp(id_empresa)
    if not _puede(usuario, "inteligencia.decidir", emp):
        return {"ok": False, "motivo": "no autorizado"}
    ok = _resolver(id_decision, emp, "rechazada", feedback=motivo, actor=_actor(usuario))
    if ok:
        _evento("DecisionRejected", emp, id_decision, {"usuario": _actor(usuario), "motivo": motivo})
    return {"ok": ok}


def feedback(id_decision, *, util=None, comentario=None, usuario=None, id_empresa=None):
    """Retroalimentación supervisada (Aprendizaje continuo): registra utilidad/comentario del usuario
    para mejorar futuras recomendaciones. NO modifica datos de negocio."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "inteligencia.ver", emp):
        return {"ok": False, "motivo": "no autorizado"}
    txt = (f"util={util}" + (f"; {comentario}" if comentario else ""))[:255]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE decisiones_ia SET feedback=%s WHERE id=%s AND id_empresa=%s",
                        (txt, id_decision, emp))
            conn.commit()
            ok = cur.rowcount > 0
    except Exception as e:
        logger.error("feedback(%s): %s", id_decision, e)
        ok = False
    if ok:
        _evento("DecisionFeedback", emp, id_decision, {"usuario": _actor(usuario), "util": util})
    return {"ok": ok}


def _actor(usuario):
    if isinstance(usuario, dict):
        return usuario.get("id") or usuario.get("nombre")
    return usuario


def descriptor() -> dict:
    _proveedores_por_defecto()
    return {"servicio": "inteligencia", "etapa": "C", "fase": FASE, "estado": "implementado",
            "capa": "transversal", "proveedores": sorted(_PROVEEDORES),
            "reutiliza": ["ia.recomendaciones", "ia.anomalias", "ia.riesgos", "ia.predicciones",
                          "rbac", "eventbus", "observabilidad"],
            "motor_ia_nuevo": False, "modifica_datos": False, "auditable": True}


__all__ = ["FASE", "registrar_proveedor", "generar", "proponer", "decisiones", "obtener", "resumen",
           "aceptar", "rechazar", "feedback", "descriptor"]
