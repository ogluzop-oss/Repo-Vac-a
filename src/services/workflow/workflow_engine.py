"""
Motor de Workflow / BPM (FASE WF-2/4/12).

Capa transversal de aprobaciones. Es ADITIVA y NO intrusiva: si una entidad no tiene una
definición activa para la empresa, `iniciar_proceso` devuelve {"workflow": False} y el dominio
sigue su curso normal (comportamiento legacy intacto). Resuelve aprobadores con RBAC/ACL
(autorizacion.puede), evalúa reglas por importe/condición, soporta multinivel, varios
aprobadores por paso (usuarios_minimos), delegaciones y SLA/escalado. Audita en auditoria_logs.
"""

import datetime as _dt
import logging

from src.db import workflow as _W

logger = logging.getLogger("workflow.engine")

EVENTOS = ("WF_INICIADO", "WF_TAREA_ASIGNADA", "WF_APROBADO", "WF_RECHAZADO",
           "WF_CANCELADO", "WF_ESCALADO", "WF_FINALIZADO", "WF_DELEGADO")


class ErrorWorkflow(RuntimeError):
    pass


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def _norm(actor):
    try:
        from src.services.autorizacion import _norm_usuario
        return _norm_usuario(actor)
    except Exception:
        return actor if isinstance(actor, dict) else None


def _audit(evento, usuario=None, detalle=None):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria(str(usuario) if usuario is not None else "sistema", evento, "workflow", detalle)
    except Exception:
        pass


def _cmp(op, a, b):
    try:
        a = float(a); b = float(b)
    except (TypeError, ValueError):
        a, b = str(a), str(b)
    return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b,
            "==": a == b, "!=": a != b}.get(op, False)


def _pasos_aplicables(definicion_id, contexto):
    """Pasos cuyo gating (reglas activar_paso) se cumple con el contexto. Los pasos sin regla
    de activación se incluyen siempre."""
    pasos = _W.pasos_de(definicion_id)
    reglas = [r for r in _W.reglas_de(definicion_id) if r["accion"] == "activar_paso" and r["id_paso"]]
    gating = {}
    for r in reglas:
        gating.setdefault(r["id_paso"], []).append(r)
    out = []
    for p in pasos:
        rs = gating.get(p["id"])
        if not rs:
            out.append(p)
            continue
        if all(_cmp(r["operador"], contexto.get(r["condicion"]), r["valor"]) for r in rs):
            out.append(p)
    return out


def _notificar(titulo, mensaje, *, roles=None, usuarios=None, prioridad="normal", id_empresa=None):
    """Emite una notificación (best-effort; COM-12). Nunca rompe el flujo del motor."""
    try:
        from src.services import notificaciones
        notificaciones.emitir("workflow", titulo, mensaje, modulo="workflow", prioridad=prioridad,
                              roles=roles, usuarios=usuarios, id_empresa=id_empresa)
    except Exception:
        pass


def _crear_tarea_paso(iid, paso, id_empresa):
    tid = _W.crear_tarea(iid, paso["id"], asignado_rol=paso.get("rol_requerido"),
                         asignado_grupo=paso.get("grupo_requerido"),
                         permiso_requerido=paso.get("permiso_requerido"), id_empresa=id_empresa)
    _W.log(iid, "WF_TAREA_ASIGNADA", detalle=f"paso={paso['orden']} {paso['nombre']}", id_empresa=id_empresa)
    _audit("WF_TAREA_ASIGNADA", detalle=f"instancia={iid} paso={paso['orden']}")
    _notificar("Tarea de aprobación pendiente", f"Paso «{paso['nombre']}» requiere tu aprobación.",
               roles=[paso["rol_requerido"]] if paso.get("rol_requerido") else None,
               prioridad="alta", id_empresa=id_empresa)
    return tid


def iniciar_proceso(entidad, entidad_id, *, contexto=None, actor=None, id_empresa=None) -> dict:
    """Inicia el circuito de `entidad` si hay definición activa. Devuelve dict con workflow:
    False (no hay circuito → seguir normal), o el estado de la instancia."""
    id_empresa = _emp(id_empresa)
    contexto = contexto or {}
    _gate("workflow", id_empresa)
    defn = _W.definicion_activa(entidad, id_empresa)
    if not defn:
        return {"workflow": False}
    iid = _W.crear_instancia(defn["id"], entidad, entidad_id, contexto=contexto, id_empresa=id_empresa)
    _W.log(iid, "WF_INICIADO", usuario=(_norm(actor) or {}).get("id"),
           detalle=f"{entidad}:{entidad_id}", id_empresa=id_empresa)
    _audit("WF_INICIADO", usuario=(_norm(actor) or {}).get("id"), detalle=f"{entidad}:{entidad_id}")
    pasos = _pasos_aplicables(defn["id"], contexto)
    if not pasos:
        # Sin pasos de aprobación aplicables (p.ej. importe bajo umbral) → aprobado directo.
        _W.actualizar_instancia(iid, estado="APROBADO", cerrar=True, id_empresa=id_empresa)
        _W.log(iid, "WF_FINALIZADO", detalle="sin aprobación requerida", id_empresa=id_empresa)
        _audit("WF_FINALIZADO", detalle=f"instancia={iid} auto-aprobada")
        return {"workflow": True, "instancia": iid, "estado": "APROBADO", "tarea": None}
    primero = pasos[0]
    _W.actualizar_instancia(iid, estado="EN_CURSO", paso_actual=primero["orden"], id_empresa=id_empresa)
    tid = _crear_tarea_paso(iid, primero, id_empresa)
    return {"workflow": True, "instancia": iid, "estado": "EN_CURSO", "tarea": tid}


# Jerarquía de roles del sistema: un rol superior puede aprobar pasos de rol inferior.
_RANGO_ROL = {"OPERARIO": 1, "GERENTE": 2, "ADMINISTRADOR": 3, "SUPERADMIN": 4}


def _actor_autorizado(tarea, actor) -> bool:
    u = _norm(actor)
    if not u or not u.get("id"):
        return True                              # flujo interno/sin sesión → no bloquea
    perfil = (u.get("perfil") or "").upper()
    if perfil == "SUPERADMIN":
        return True
    # Permiso (RBAC) requerido por el paso.
    if tarea.get("permiso_requerido"):
        try:
            from src.services import autorizacion
            if autorizacion.puede(actor, tarea["permiso_requerido"]):
                return True
        except Exception:
            pass
    # Rol requerido: coincidencia exacta o rol superior en la jerarquía.
    if tarea.get("asignado_rol"):
        req = tarea["asignado_rol"].upper()
        if perfil == req or _RANGO_ROL.get(perfil, 0) >= _RANGO_ROL.get(req, 99):
            return True
    if tarea.get("asignado_usuario") and u.get("id") == tarea["asignado_usuario"]:
        return True
    # Delegación: el actor es destino de una delegación del usuario asignado.
    if tarea.get("asignado_usuario"):
        if u.get("id") in _W.delegados_de(tarea["asignado_usuario"], tarea.get("id_empresa")):
            return True
    return False


def _paso_de(iid, id_paso, id_empresa):
    inst = _W.obtener_instancia(iid, id_empresa)
    for p in _W.pasos_de(inst["id_definicion"]):
        if p["id"] == id_paso:
            return p, inst
    return None, inst


def aprobar_tarea(id_tarea, *, actor=None, comentario=None, id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    tarea = _W.obtener_tarea(id_tarea, id_empresa)
    if not tarea or tarea["estado"] != "PENDIENTE":
        raise ErrorWorkflow("tarea no pendiente")
    if not _actor_autorizado(tarea, actor):
        from src.db.conexion import log_auditoria
        try:
            log_auditoria(str((_norm(actor) or {}).get("id")), "WF_DENEGADO", "workflow",
                          f"tarea={id_tarea}")
        except Exception:
            pass
        raise PermissionError("No autorizado para aprobar esta tarea")
    uid = (_norm(actor) or {}).get("id")
    _W.resolver_tarea(id_tarea, "APROBADA", uid, comentario, id_empresa)
    iid = tarea["id_instancia"]
    _W.log(iid, "WF_APROBADO", usuario=uid, detalle=f"tarea={id_tarea}", id_empresa=id_empresa)
    _audit("WF_APROBADO", usuario=uid, detalle=f"tarea={id_tarea}")
    paso, inst = _paso_de(iid, tarea["id_paso"], id_empresa)
    # ¿El paso necesita más aprobadores (usuarios_minimos)?
    aprobadas = [t for t in _W.tareas_de_instancia(iid, id_empresa=id_empresa)
                 if t["id_paso"] == tarea["id_paso"] and t["estado"] == "APROBADA"]
    if paso and len(aprobadas) < int(paso.get("usuarios_minimos") or 1):
        ntid = _crear_tarea_paso(iid, paso, id_empresa)   # siguiente aprobador del mismo paso
        return {"estado": "EN_CURSO", "tarea": ntid, "instancia": iid}
    # Paso satisfecho → avanzar al siguiente aplicable.
    contexto = inst.get("contexto", {})
    pasos = _pasos_aplicables(inst["id_definicion"], contexto)
    ordenes = [p["orden"] for p in pasos]
    actual = paso["orden"] if paso else inst.get("paso_actual")
    siguientes = [p for p in pasos if p["orden"] > actual]
    if siguientes:
        nxt = siguientes[0]
        _W.actualizar_instancia(iid, paso_actual=nxt["orden"], id_empresa=id_empresa)
        ntid = _crear_tarea_paso(iid, nxt, id_empresa)
        return {"estado": "EN_CURSO", "tarea": ntid, "instancia": iid}
    _W.actualizar_instancia(iid, estado="APROBADO", cerrar=True, id_empresa=id_empresa)
    _W.log(iid, "WF_FINALIZADO", usuario=uid, detalle="aprobado", id_empresa=id_empresa)
    _audit("WF_FINALIZADO", usuario=uid, detalle=f"instancia={iid}")
    return {"estado": "APROBADO", "tarea": None, "instancia": iid}


def rechazar_tarea(id_tarea, *, actor=None, comentario=None, id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    tarea = _W.obtener_tarea(id_tarea, id_empresa)
    if not tarea or tarea["estado"] != "PENDIENTE":
        raise ErrorWorkflow("tarea no pendiente")
    if not _actor_autorizado(tarea, actor):
        raise PermissionError("No autorizado para rechazar esta tarea")
    uid = (_norm(actor) or {}).get("id")
    _W.resolver_tarea(id_tarea, "RECHAZADA", uid, comentario, id_empresa)
    iid = tarea["id_instancia"]
    _W.actualizar_instancia(iid, estado="RECHAZADO", cerrar=True, id_empresa=id_empresa)
    _W.log(iid, "WF_RECHAZADO", usuario=uid, detalle=comentario, id_empresa=id_empresa)
    _audit("WF_RECHAZADO", usuario=uid, detalle=f"instancia={iid}")
    return {"estado": "RECHAZADO", "instancia": iid}


def cancelar_flujo(id_instancia, *, actor=None, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    _W.actualizar_instancia(id_instancia, estado="CANCELADO", cerrar=True, id_empresa=id_empresa)
    for t in _W.tareas_de_instancia(id_instancia, estado="PENDIENTE", id_empresa=id_empresa):
        _W.resolver_tarea(t["id"], "CANCELADA", (_norm(actor) or {}).get("id"), None, id_empresa)
    _W.log(id_instancia, "WF_CANCELADO", usuario=(_norm(actor) or {}).get("id"), id_empresa=id_empresa)
    _audit("WF_CANCELADO", detalle=f"instancia={id_instancia}")
    return True


def estado_entidad(entidad, entidad_id, id_empresa=None) -> str | None:
    inst = _W.instancia_por_entidad(entidad, entidad_id, id_empresa)
    return inst["estado"] if inst else None


def aprobado(entidad, entidad_id, id_empresa=None) -> bool:
    """True si la entidad está aprobada o NO tiene workflow (legacy → no bloquea)."""
    inst = _W.instancia_por_entidad(entidad, entidad_id, id_empresa)
    if not inst:
        return True
    return inst["estado"] == "APROBADO"


def tareas_para_usuario(actor, *, estado="PENDIENTE", id_empresa=None) -> list:
    """Tareas (bandeja) sobre las que el actor puede actuar (permiso/rol/usuario/delegación)."""
    id_empresa = _emp(id_empresa)
    return [t for t in _W.tareas_pendientes(estado=estado, id_empresa=id_empresa)
            if _actor_autorizado(t, actor)]


# ── SLA / escalado (FASE WF-12) ──────────────────────────────────────────────
def procesar_sla(id_empresa=None) -> dict:
    """Detecta tareas pendientes que han superado el SLA de su paso y registra escalado.
    Devuelve {escaladas}. Idempotente por marca en el log (best-effort)."""
    id_empresa = _emp(id_empresa)
    res = {"escaladas": 0}
    ahora = _dt.datetime.now()
    for t in _W.tareas_pendientes(id_empresa=id_empresa):
        paso, _inst = _paso_de(t["id_instancia"], t["id_paso"], id_empresa)
        sla = (paso or {}).get("sla_horas")
        if not sla:
            continue
        creada = t.get("fecha_creacion")
        if isinstance(creada, str):
            try:
                creada = _dt.datetime.strptime(creada[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
        if creada and (ahora - creada).total_seconds() > int(sla) * 3600:
            _W.log(t["id_instancia"], "WF_ESCALADO", detalle=f"tarea={t['id']} SLA={sla}h", id_empresa=id_empresa)
            _audit("WF_ESCALADO", detalle=f"tarea={t['id']}")
            res["escaladas"] += 1
    return res

def _gate(modulo, id_empresa):
    """Enforcement SaaS (legacy-safe): bloquea si el plan no incluye el módulo."""
    try:
        from src.services.saas import enforcement as _enf
        _enf.exigir_modulo(modulo, id_empresa)
    except ImportError:
        pass
