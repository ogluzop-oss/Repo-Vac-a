"""
Motor de Orquestacion Empresarial (Paquete Enterprise 4, SUBFASE 4.1) — `AutomationService`.

El cerebro de automatizacion: NUNCA actua directamente ni escribe en el ERP. Decide QUE hacer,
CUANDO, con que PRIORIDAD, si necesita APROBACION (Workflow/BPM) o si puede EJECUTARSE (solo si
esta configurado). Reutiliza reglas + acciones (que delegan en Workflow/notificaciones/propuestas),
Event Bus, IA y PredictionService. Asincrono (SUBFASE 4.12): se invoca desde el scheduler o un
hilo, nunca en la ruta de TPV/Facturacion. Todo auditable (SUBFASE 4.10).
"""

import hashlib
import json
import logging
import threading
from datetime import date

from src.services.automatizacion import (acciones, configuracion, niveles,
                                         reglas)

logger = logging.getLogger("automatizacion.motor")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


class AutomationService:

    # ── Ejecucion de una regla disparada (decision + accion + auditoria) ──
    def _disparar(self, regla, ctx, id_empresa, *, trigger_ref, usuario=None) -> dict:
        emp = _emp(id_empresa)
        nivel = niveles.normalizar(regla.get("nivel"))
        accion = regla.get("accion")
        try:
            params = json.loads(regla.get("params")) if regla.get("params") else None
        except Exception:
            params = None
        motivo = ctx.get("mensaje") or regla.get("nombre") or regla.get("codigo")
        prioridad = ctx.get("prioridad", regla.get("prioridad", "MEDIA"))
        ctx = {**ctx, "prioridad": prioridad}
        estado = niveles.ESTADO_POR_NIVEL.get(nivel, "PROPUESTA")
        resultado = ""

        if nivel == niveles.INFORMAR:
            resultado = acciones.notificar(ctx, {"modulo": (params or {}).get("modulo", "automatizacion"),
                                                 "titulo": regla.get("nombre")}, emp)
        elif nivel == niveles.PROPONER:
            resultado = acciones.ejecutar(accion, ctx, params, emp)   # acciones "propuesta" son seguras
        elif nivel == niveles.APROBAR:
            resultado = acciones.solicitar_aprobacion(ctx, params or {"entidad": regla.get("codigo")}, emp)
        elif nivel == niveles.AUTO:
            if niveles.permite_ejecutar(nivel, accion,
                                        auto_critico=configuracion.auto_critico_permitido(emp)):
                resultado = acciones.ejecutar(accion, ctx, params, emp)
                estado = "EJECUTADA"
            else:
                # Accion critica sin autorizacion → degrada a propuesta (nunca ejecuta).
                resultado = acciones.ejecutar("notificar", ctx,
                                              {"modulo": "automatizacion",
                                               "titulo": f"[Propuesta] {regla.get('nombre')}"}, emp)
                estado = "PROPUESTA"

        eid = self._registrar(regla, emp, trigger_ref, accion, nivel, estado, motivo, resultado, usuario)
        # Publica en el Event Bus (feeds Centro/Timeline/Badge) — best-effort.
        try:
            from src.services import eventos as _EV
            _EV.publicar("AUTOMATIZACION_EJECUTADA", id_empresa=emp, origen="automatizacion",
                         prioridad=prioridad, ref_entidad="automatizacion", ref_id=regla.get("codigo"),
                         payload={"regla": regla.get("codigo"), "accion": accion, "nivel": nivel,
                                  "estado": estado, "motivo": motivo})
        except Exception:
            pass
        return {"regla": regla.get("codigo"), "nivel": nivel, "estado": estado, "accion": accion,
                "resultado": resultado, "motivo": motivo, "id": eid}

    def _registrar(self, regla, emp, trigger_ref, accion, nivel, estado, motivo, resultado, usuario) -> int | None:
        # Idempotencia: una ejecucion por (regla, trigger_ref, dia).
        h = hashlib.sha256(f"{regla.get('codigo')}|{trigger_ref}|{date.today()}".encode()).hexdigest()
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute(
                    "INSERT IGNORE INTO automatizaciones_ejecuciones (id_empresa, codigo_regla, "
                    "trigger_tipo, trigger_ref, accion, nivel, estado, motivo, usuario, "
                    "ref_entidad, ref_id, resultado, hash) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (emp, regla.get("codigo"), regla.get("trigger_tipo"), trigger_ref, accion, nivel,
                     estado, (motivo or "")[:255], usuario, "automatizacion", regla.get("codigo"),
                     (resultado or "")[:255], h))
                eid = cur.lastrowid
                c.commit()
                return eid
        except Exception as e:
            logger.error("_registrar: %s", e)
            return None

    def _procesar(self, id_empresa, *, trigger_tipo, trigger_valor=None, trigger_ref_pref="") -> list:
        emp = _emp(id_empresa)
        if not configuracion.activo(emp):
            return []
        out = []
        for r in reglas.listar_activas(emp, trigger_tipo=trigger_tipo, trigger_valor=trigger_valor):
            disparada, ctx = reglas.evaluar(r, emp)
            if disparada:
                ref = f"{trigger_ref_pref}{r.get('codigo')}"
                out.append(self._disparar(r, ctx, emp, trigger_ref=ref))
        return out

    # ── Disparadores (SUBFASE 4.3/4.4/4.6) ──
    def procesar_evento(self, evento, id_empresa=None) -> list:
        """Automatizacion por EVENTO (Event Bus dispara reglas)."""
        emp = _emp(id_empresa)
        if not configuracion.activo(emp):
            return []
        tipo = evento.get("tipo") if isinstance(evento, dict) else str(evento)
        out = []
        for r in reglas.listar_activas(emp, trigger_tipo="evento", trigger_valor=tipo):
            disparada, ctx = reglas.evaluar(r, emp)
            if disparada:
                ctx = {**ctx, "mensaje": ctx.get("mensaje") or f"Evento {tipo}"}
                ref = f"evento:{(evento.get('id') if isinstance(evento, dict) else tipo)}:{r.get('codigo')}"
                out.append(self._disparar(r, ctx, emp, trigger_ref=ref))
        return out

    def procesar_predicciones(self, id_empresa=None) -> list:
        """Automatizacion por PREDICCION (PredictionService dispara reglas)."""
        return self._procesar(id_empresa, trigger_tipo="prediccion",
                              trigger_ref_pref="prediccion:")

    def procesar_programadas(self, id_empresa=None, cuando="diario") -> list:
        """Automatizaciones programadas (diario/semanal/mensual)."""
        return self._procesar(id_empresa, trigger_tipo="programado", trigger_valor=cuando,
                              trigger_ref_pref=f"programado:{cuando}:")

    def tick(self, id_empresa=None) -> dict:
        """Ciclo completo (asincrono): programadas diarias + predicciones."""
        return {"programadas": self.procesar_programadas(id_empresa, "diario"),
                "predicciones": self.procesar_predicciones(id_empresa)}

    def procesar_async(self, id_empresa=None) -> None:
        """SUBFASE 4.12: ejecuta el tick en un hilo daemon (nunca bloquea el ERP)."""
        threading.Thread(target=lambda: self.tick(id_empresa), daemon=True).start()

    # ── Aprobacion/rechazo desde el panel ──
    def _cambiar_estado(self, id_ejecucion, nuevo, id_empresa=None, usuario=None) -> bool:
        emp = _emp(id_empresa)
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("UPDATE automatizaciones_ejecuciones SET estado=%s, usuario=COALESCE(%s,usuario) "
                            "WHERE id=%s AND id_empresa=%s", (nuevo, usuario, id_ejecucion, emp))
                c.commit()
            return True
        except Exception as e:
            logger.error("cambiar_estado: %s", e)
            return False

    def aprobar(self, id_ejecucion, id_empresa=None, usuario=None) -> bool:
        return self._cambiar_estado(id_ejecucion, "APROBADA", id_empresa, usuario)

    def rechazar(self, id_ejecucion, id_empresa=None, usuario=None) -> bool:
        return self._cambiar_estado(id_ejecucion, "RECHAZADA", id_empresa, usuario)


_service = AutomationService()


def servicio() -> AutomationService:
    return _service
