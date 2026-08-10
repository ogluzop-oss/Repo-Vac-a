"""
Ejecucion por fases y reversion (Paquete Enterprise 10, SUBFASE 10.5/10.6/10.15).

Nunca ejecuta todo a la vez: divide el plan en FASES y valida entre cada una (10.5). Cada accion
guarda su estado previo para poder REVERTIRSE (10.6). Todo queda AUDITADO (10.15): quien, cuando,
que, por que, resultado, reversion. Respeta el MODO de empresa (10.13) y la seguridad (10.14): las
acciones criticas nunca se auto-ejecutan (se convierten en propuesta gobernada).

La ejecucion exige un plan APROBADO (lo verifica validaciones.validar). Reutiliza el catalogo de
AutomationService; no escribe en datos operativos.
"""

import hashlib
import json
import logging

from src.services.autonomia import catalogo, modos, validaciones
from src.services.autonomia import modelo as M

logger = logging.getLogger("autonomia.ejecucion")


def _emp(id_empresa=None):
    return modos._emp(id_empresa)


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("autonomia", accion, tabla_afectada="exec_acciones", detalles=detalle[:500])
    except Exception:
        pass


def _hash(*p):
    return hashlib.sha256("|".join(str(x) for x in p).encode("utf-8")).hexdigest()


def _fases_de(acciones) -> list:
    return sorted({int(a.get("fase", 1)) for a in acciones})


def ejecutar_accion(accion, *, usuario, modo, id_empresa) -> dict:
    """Ejecuta UNA accion respetando modo/seguridad. Guarda estado previo y resultado. Auditada."""
    emp = id_empresa
    codigo = accion["codigo_accion"]
    meta = catalogo.meta(codigo)
    try:
        params = json.loads(accion.get("params_json") or "{}")
    except Exception:
        params = {}

    permite = modos.permite_ejecucion(modo, critica=meta["critica"], informativa=meta["informativa"])
    ctx = {"mensaje": accion.get("titulo") or codigo, "prioridad": "MEDIA", "ref_id": accion["id"],
           "usuario": usuario}
    estado_previo = {"estado": accion.get("estado"), "modo": modo}

    if meta["critica"] or not permite:
        # Seguridad 10.14 / limite de modo 10.13: NO se ejecuta; se propone (gobernado).
        resultado = catalogo.ejecutar(codigo, ctx, params, emp) if meta["critica"] else \
            f"OMITIDA por modo {modo} (accion no permitida para auto-ejecucion)"
        nuevo_estado = M.ACC_OMITIDA
    else:
        resultado = catalogo.ejecutar(codigo, ctx, params, emp)
        nuevo_estado = M.ACC_EJECUTADA

    _persistir_estado(accion["id"], emp, nuevo_estado, estado_previo, resultado)
    _audit("ACCION_" + nuevo_estado,
           f"plan={accion['id_plan']} accion={codigo} usuario={usuario} modo={modo} -> {resultado}")
    return {"id": accion["id"], "codigo": codigo, "estado": nuevo_estado, "resultado": resultado,
            "critica": meta["critica"]}


def _persistir_estado(id_accion, emp, estado, estado_previo, resultado):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            campo_fecha = "ejecutado=NOW()" if estado == M.ACC_EJECUTADA else "ejecutado=ejecutado"
            cur.execute(f"UPDATE exec_acciones SET estado=%s, estado_previo_json=%s, resultado=%s, "
                        f"hash=%s, {campo_fecha} WHERE id=%s AND id_empresa=%s",
                        (estado, json.dumps(estado_previo, default=str), (resultado or "")[:255],
                         _hash(id_accion, estado, resultado), id_accion, emp))
            c.commit()
    except Exception as e:
        logger.debug("persistir estado accion: %s", e)


def ejecutar_fase(plan, fase, *, usuario, perfil, id_empresa) -> dict:
    """Ejecuta las acciones de UNA fase (tras validar). Devuelve el resultado de la fase."""
    emp = id_empresa
    val = validaciones.validar(plan, usuario=usuario, perfil=perfil, id_empresa=emp)
    if not val["ok"]:
        return {"fase": fase, "ejecutada": False, "motivo": val["motivo"], "validacion": val}
    modo = plan.get("modo") or modos.obtener(emp)
    acciones = [a for a in plan.get("acciones", [])
                if int(a.get("fase", 1)) == fase and a.get("estado") in (M.ACC_PENDIENTE, M.ACC_VALIDADA)]
    resultados = [ejecutar_accion(a, usuario=usuario, modo=modo, id_empresa=emp) for a in acciones]
    return {"fase": fase, "ejecutada": True, "acciones": resultados,
            "ejecutadas": len([r for r in resultados if r["estado"] == M.ACC_EJECUTADA]),
            "propuestas": len([r for r in resultados if r["estado"] == M.ACC_OMITIDA])}


def ejecutar_plan(plan, *, usuario, perfil, id_empresa, solo_fase=None) -> dict:
    """SUBFASE 10.5: ejecucion por fases con validacion entre cada una. `solo_fase` limita a una."""
    from src.services.autonomia import planes as _P
    emp = id_empresa
    fases = _fases_de(plan.get("acciones", []))
    if solo_fase is not None:
        fases = [f for f in fases if f == int(solo_fase)]
    _P.marcar(plan["id"], M.EN_EJECUCION, id_empresa=emp)
    _audit("PLAN_EN_EJECUCION", f"plan={plan['id']} usuario={usuario} fases={fases}")

    resultados_fase = []
    for f in fases:
        # Recargar el plan para tomar los estados actualizados de las acciones.
        plan_actual = _P.obtener(plan["id"], emp) or plan
        rf = ejecutar_fase(plan_actual, f, usuario=usuario, perfil=perfil, id_empresa=emp)
        resultados_fase.append(rf)
        if not rf.get("ejecutada"):
            _P.marcar(plan["id"], M.CANCELADO, id_empresa=emp)
            _audit("PLAN_CANCELADO", f"plan={plan['id']} fase={f} motivo={rf.get('motivo')}")
            return {"id_plan": plan["id"], "estado": M.CANCELADO, "fases": resultados_fase,
                    "motivo": rf.get("motivo")}

    # Estado final: EJECUTADO (todas las fases pasadas) o PARCIAL (si solo una fase).
    plan_final = _P.obtener(plan["id"], emp) or plan
    pendientes = [a for a in plan_final.get("acciones", [])
                  if a.get("estado") in (M.ACC_PENDIENTE, M.ACC_VALIDADA)]
    estado_final = M.PARCIAL if (solo_fase is not None and pendientes) else M.EJECUTADO
    _P.marcar(plan["id"], estado_final, id_empresa=emp)
    _audit("PLAN_" + estado_final, f"plan={plan['id']} usuario={usuario}")
    return {"id_plan": plan["id"], "estado": estado_final, "fases": resultados_fase}


def revertir_plan(id_plan, *, usuario, id_empresa) -> dict:
    """SUBFASE 10.6: revierte las acciones ejecutadas reversibles del plan. Auditado."""
    from src.services.autonomia import planes as _P
    emp = id_empresa
    plan = _P.obtener(id_plan, emp)
    if not plan:
        return {"error": "plan no encontrado"}
    revertidas = 0
    for a in plan.get("acciones", []):
        if a.get("estado") != M.ACC_EJECUTADA:
            continue
        if not a.get("reversible"):
            continue
        try:
            params = json.loads(a.get("params_json") or "{}")
        except Exception:
            params = {}
        res = catalogo.revertir(a["codigo_accion"], {"usuario": usuario}, params, emp)
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("UPDATE exec_acciones SET estado=%s, resultado=%s, revertido=NOW() "
                            "WHERE id=%s AND id_empresa=%s",
                            (M.ACC_REVERTIDA, (res or "")[:255], a["id"], emp))
                c.commit()
            revertidas += 1
        except Exception as e:
            logger.debug("revertir accion: %s", e)
        _audit("ACCION_REVERTIDA", f"plan={id_plan} accion={a['codigo_accion']} usuario={usuario}")
    _P.marcar(id_plan, M.REVERTIDO, id_empresa=emp)
    _audit("PLAN_REVERTIDO", f"plan={id_plan} usuario={usuario} revertidas={revertidas}")
    return {"id_plan": id_plan, "estado": M.REVERTIDO, "revertidas": revertidas}
