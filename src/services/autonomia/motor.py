"""
ExecutiveActionService (Paquete Enterprise 10, SUBFASE 10.1) — FACHADA PUBLICA UNICA y UNICO
servicio autorizado para EJECUTAR acciones reales. Ningun otro modulo puede ejecutar directamente.

La IA propone, la organizacion decide, el sistema ejecuta solo lo autorizado. Toda ejecucion exige:
un plan APROBADO, autoridad de Gobierno Corporativo, aprobacion de Workflow (si aplica) y un modo de
empresa que lo permita; las acciones criticas nunca se auto-ejecutan (se proponen). Coordina
Simulador, Workflow/BPM, Gobierno, AutomationService, Agentes, IA y Gemelo Digital — sin duplicar
ninguno. Todo auditado.
"""

import logging

from src.services.autonomia import (agentes_revision, dashboard, ejecucion,
                                    explicabilidad, indicador, modos, planes,
                                    seguridad, validaciones)
from src.services.autonomia import modelo as M

logger = logging.getLogger("autonomia.motor")


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("autonomia", accion, tabla_afectada="exec_planes", detalles=detalle[:500])
    except Exception:
        pass


class ExecutiveActionService:

    # ── Planes (10.2/10.3) ──
    def crear_plan(self, nombre, **k):
        return planes.crear(nombre, **k)

    def plan_desde_escenario(self, id_escenario, *, usuario=None, id_empresa=None):
        return planes.crear_desde_escenario(id_escenario, usuario=usuario, id_empresa=id_empresa)

    def plan(self, id_plan, id_empresa=None):
        return planes.obtener(id_plan, id_empresa)

    def planes(self, id_empresa=None, *, estado=None):
        return planes.listar(id_empresa, estado=estado)

    def detalle_plan(self, id_plan, id_empresa=None):
        return planes.detalle(id_plan, id_empresa)

    # ── Explicabilidad (10.7) + Revision por agentes (10.8) ──
    def explicar(self, id_plan, id_empresa=None) -> dict:
        return explicabilidad.explicar(planes.detalle(id_plan, id_empresa))

    def revisar_con_agentes(self, id_plan, *, usuario=None, perfil="ADMINISTRADOR", id_empresa=None):
        return agentes_revision.revisar(planes.detalle(id_plan, id_empresa), usuario=usuario,
                                        perfil=perfil, id_empresa=id_empresa)

    # ── Circuito de aprobacion (Workflow + Gobierno) ──
    def solicitar_aprobacion(self, id_plan, *, usuario=None, perfil="ADMINISTRADOR", id_empresa=None) -> dict:
        """Envia el plan al circuito de Workflow/BPM. Queda PENDIENTE_APROBACION."""
        emp = modos._emp(id_empresa)
        wf_ref = None
        try:
            from src.services.workflow import workflow_engine as WF
            r = WF.iniciar_proceso("plan_ejecucion", id_plan,
                                   contexto={"plan": id_plan, "usuario": usuario}, id_empresa=emp)
            wf_ref = r.get("instancia")
            # Si el workflow auto-aprueba (sin pasos), el plan puede aprobarse directamente despues.
        except Exception as e:
            logger.debug("solicitar_aprobacion workflow: %s", e)
        planes.marcar(id_plan, M.PENDIENTE_APROBACION, workflow_ref=wf_ref, id_empresa=emp)
        _audit("PLAN_SOLICITA_APROBACION", f"plan={id_plan} usuario={usuario} wf={wf_ref}")
        return {"id_plan": id_plan, "estado": M.PENDIENTE_APROBACION, "workflow_ref": wf_ref}

    def aprobar_plan(self, id_plan, *, usuario=None, perfil="ADMINISTRADOR", id_empresa=None) -> dict:
        """La ORGANIZACION decide: aprueba el plan si el usuario tiene autoridad de Gobierno y el
        workflow (si existe) esta aprobado. Solo entonces el plan puede ejecutarse."""
        emp = modos._emp(id_empresa)
        # Autoridad de Gobierno Corporativo.
        try:
            from src.services import gobierno
            g = gobierno.servicio().puede_aprobar(usuario or "sistema", "autonomia", 0, emp, perfil)
            if not g.get("permitido", False):
                return {"id_plan": id_plan, "aprobado": False, "motivo": g.get("motivo", "sin autoridad")}
        except Exception as e:
            logger.debug("aprobar_plan gobierno: %s", e)
        # Workflow (si hay instancia, debe estar aprobado).
        try:
            from src.services.workflow import workflow_engine as WF
            if not WF.aprobado("plan_ejecucion", id_plan, emp):
                return {"id_plan": id_plan, "aprobado": False, "motivo": "workflow no aprobado"}
        except Exception:
            pass
        planes.marcar(id_plan, M.APROBADO, aprobado_por=usuario, id_empresa=emp)
        _audit("PLAN_APROBADO", f"plan={id_plan} aprobado_por={usuario} perfil={perfil}")
        return {"id_plan": id_plan, "aprobado": True, "estado": M.APROBADO}

    def cancelar_plan(self, id_plan, *, usuario=None, id_empresa=None) -> dict:
        emp = modos._emp(id_empresa)
        planes.marcar(id_plan, M.CANCELADO, id_empresa=emp)
        _audit("PLAN_CANCELADO", f"plan={id_plan} usuario={usuario}")
        return {"id_plan": id_plan, "estado": M.CANCELADO}

    # ── Validacion (10.4) ──
    def validar(self, id_plan, *, usuario=None, perfil="ADMINISTRADOR", id_empresa=None) -> dict:
        emp = modos._emp(id_empresa)
        plan = planes.obtener(id_plan, emp)
        if not plan:
            return {"ok": False, "motivo": "plan no encontrado"}
        return validaciones.validar(plan, usuario=usuario, perfil=perfil, id_empresa=emp)

    # ── Ejecucion por fases (10.5) + Reversion (10.6) ──
    def ejecutar(self, id_plan, *, usuario=None, perfil="ADMINISTRADOR", id_empresa=None, solo_fase=None) -> dict:
        emp = modos._emp(id_empresa)
        plan = planes.obtener(id_plan, emp)
        if not plan:
            return {"error": "plan no encontrado"}
        if plan.get("estado") not in (M.APROBADO, M.EN_EJECUCION, M.PARCIAL):
            return {"error": f"el plan debe estar APROBADO (estado actual: {plan.get('estado')})",
                    "estado": plan.get("estado")}
        return ejecucion.ejecutar_plan(plan, usuario=usuario, perfil=perfil, id_empresa=emp,
                                       solo_fase=solo_fase)

    def revertir(self, id_plan, *, usuario=None, id_empresa=None) -> dict:
        emp = modos._emp(id_empresa)
        return ejecucion.revertir_plan(id_plan, usuario=usuario, id_empresa=emp)

    # ── Modo de empresa (10.13) ──
    def modo(self, id_empresa=None) -> str:
        return modos.obtener(id_empresa)

    def establecer_modo(self, modo, id_empresa=None) -> bool:
        return modos.establecer(modo, id_empresa)

    # ── Indicador de autonomia (10.12) + Dashboard (10.11) ──
    def indicador_autonomia(self, id_empresa=None) -> dict:
        return indicador.nivel(id_empresa)

    def dashboard(self, id_empresa=None) -> dict:
        return dashboard.panel(id_empresa)

    # ── Seguridad (10.14) ──
    def seguridad(self) -> dict:
        return seguridad.garantia()

    # ── Recomendacion IA sobre el plan (10.10) ──
    def recomendacion_ia(self, id_plan, id_empresa=None) -> dict:
        emp = modos._emp(id_empresa)
        det = planes.detalle(id_plan, emp)
        criticas = det.get("acciones_criticas", [])
        riesgo = det.get("riesgo", "BAJO")
        recomendable = (riesgo != "ALTO") and (det.get("confianza") != "BAJA")
        texto = (f"{'Recomendable' if recomendable else 'Revisar antes'}: riesgo {riesgo}, "
                 f"confianza {det.get('confianza')}, {len(criticas)} accion(es) critica(s) que "
                 f"requeriran aprobacion. Tiempo estimado {det.get('tiempo_estimado_min', 0)} min.")
        return {"id_plan": id_plan, "recomendable": recomendable, "riesgo": riesgo,
                "acciones_criticas": criticas, "texto": texto,
                "tareas_a_revisar": criticas, "fuentes": ["IAService", "SimulationService", "Gobierno"]}


_service = ExecutiveActionService()


def servicio() -> ExecutiveActionService:
    return _service
