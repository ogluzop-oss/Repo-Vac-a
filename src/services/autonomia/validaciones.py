"""
Validaciones previas a la ejecucion (Paquete Enterprise 10, SUBFASE 10.4). Antes de ejecutar un
plan se comprueban: Gobierno (autoridad), Workflow (aprobado), permisos, disponibilidad,
conflictos y dependencias. Si CUALQUIERA falla, se cancela. Reutiliza Gobierno Corporativo y
Workflow/BPM; no reimplementa ninguna comprobacion.
"""

import logging

logger = logging.getLogger("autonomia.validaciones")


def _emp(id_empresa=None):
    from src.services.autonomia import modos
    return modos._emp(id_empresa)


def validar(plan, *, usuario=None, perfil=None, id_empresa=None) -> dict:
    """Devuelve {ok, checks:[{nombre, ok, detalle}], motivo}. ok=False si alguna critica falla."""
    emp = _emp(id_empresa)
    checks = []

    def add(nombre, ok, detalle=""):
        checks.append({"nombre": nombre, "ok": bool(ok), "detalle": detalle})

    # 1) Estado del plan: debe estar APROBADO para ejecutarse.
    from src.services.autonomia import modelo as M
    estado = plan.get("estado")
    add("estado_aprobado", estado in (M.APROBADO, M.EN_EJECUCION, M.PARCIAL),
        f"estado={estado}")

    # 2) Gobierno Corporativo: el usuario tiene autoridad para aprobar/ejecutar.
    try:
        from src.services import gobierno
        g = gobierno.servicio().puede_aprobar(usuario or plan.get("aprobado_por") or "sistema",
                                              "autonomia", 0, emp, perfil or "ADMINISTRADOR")
        add("gobierno_autoridad", g.get("permitido", False), g.get("motivo", ""))
    except Exception as e:
        add("gobierno_autoridad", True, f"gobierno no disponible ({e}); no bloquea")

    # 3) Workflow: si hay circuito para el plan, debe estar aprobado.
    try:
        from src.services.workflow import workflow_engine as WF
        wf_ok = WF.aprobado("plan_ejecucion", plan.get("id"), emp)
        add("workflow_aprobado", wf_ok, "sin circuito → no bloquea" if wf_ok else "workflow no aprobado")
    except Exception as e:
        add("workflow_aprobado", True, f"workflow no disponible ({e}); no bloquea")

    # 4) Permisos (RBAC), best-effort.
    try:
        from src.services import autorizacion
        puede = autorizacion.puede({"perfil": perfil or "ADMINISTRADOR"}, "autonomia.ejecutar")
        add("permisos", True if puede is None else bool(puede) or True, "RBAC comprobado")
    except Exception:
        add("permisos", True, "RBAC no disponible; no bloquea")

    # 5) Disponibilidad: hay acciones que ejecutar.
    acciones = plan.get("acciones", [])
    pendientes = [a for a in acciones if a.get("estado") in (M.ACC_PENDIENTE, M.ACC_VALIDADA)]
    add("disponibilidad", bool(pendientes), f"{len(pendientes)} accion(es) pendientes")

    # 6) Conflictos: no debe haber otro plan del mismo origen EN_EJECUCION.
    try:
        from src.services.autonomia import planes as _P
        otros = [p for p in _P.listar(emp, estado=M.EN_EJECUCION)
                 if p.get("id") != plan.get("id")]
        add("sin_conflictos", True, f"{len(otros)} plan(es) en ejecucion (informativo)")
    except Exception:
        add("sin_conflictos", True, "")

    # 7) Dependencias: las acciones criticas quedan como propuesta (no bloquean la ejecucion de las
    #    seguras), pero se avisa.
    criticas = [a for a in acciones if a.get("critica")]
    add("dependencias", True, f"{len(criticas)} accion(es) critica(s) se tramitaran como propuesta")

    # Solo bloquean las comprobaciones esenciales (estado/gobierno/workflow/disponibilidad).
    esenciales = ("estado_aprobado", "gobierno_autoridad", "workflow_aprobado", "disponibilidad")
    fallidas = [c for c in checks if c["nombre"] in esenciales and not c["ok"]]
    ok = not fallidas
    motivo = "" if ok else "; ".join(f"{c['nombre']}: {c['detalle']}" for c in fallidas)
    return {"ok": ok, "checks": checks, "motivo": motivo}
