"""
Agentes especializados (Paquete Enterprise 6, SUBFASE 6.2-6.10). Cada clase es un especialista
que REUTILIZA los servicios Enterprise (IA/Prediccion/Automatizacion/Actividad/BI) — nunca accede
a la BD ni duplica logica. Todas las respuestas son explicables (agente + fuentes + datos).
"""

from src.services.agentes.base import Agente, respuesta


class AgenteComercial(Agente):
    nombre = "comercial"; titulo = "Agente Comercial"; dominios = ("ventas", "crm")

    def responder(self, consulta, ctx, *, manager=None):
        t = (consulta or "").lower(); emp = self._emp(ctx)
        if any(k in t for k in ("inactiv", "dejando", "dejan de", "perdiendo")):
            cl = self._prediccion().clientes(emp)
            n = (cl.get("clientes") or {}).get("inactivos", 0)
            return respuesta(self.nombre, f"{n} clientes inactivos detectados; conviene contactarlos "
                             "o lanzar una campana de recuperacion.", fuentes=["CRM", "PredictionService"],
                             datos=cl)
        if any(k in t for k in ("margen", "rentab", "kpi")):
            from src.services import ia
            bi = ia.servicio().analisis_bi(emp)
            return respuesta(self.nombre, "Interpretacion de margen y KPIs comerciales disponible.",
                             fuentes=["BI", "IAService"], datos=bi)
        base = self._ia(consulta, ctx)
        return respuesta(self.nombre, base.get("texto", ""), fuentes=["Ventas", "CRM", "IAService"],
                         datos=base.get("datos"))


class AgenteCompras(Agente):
    nombre = "compras"; titulo = "Agente de Compras"; dominios = ("compras",)

    def responder(self, consulta, ctx, *, manager=None):
        emp = self._emp(ctx); comp = self._prediccion().compras(emp)
        recs = comp.get("recomendaciones", [])
        # Colaboracion entre agentes (SUBFASE 6.11): contexto de inventario.
        inv = manager.consultar("stock", "roturas", ctx) if manager else {}
        extra = f" {inv.get('texto', '')}" if inv.get("texto") else ""
        return respuesta(self.nombre, f"{len(recs)} recomendaciones de aprovisionamiento.{extra}".strip(),
                         fuentes=["Compras", "PredictionService", "AutomationService"], datos=comp)


class AgenteInventario(Agente):
    nombre = "inventario"; titulo = "Agente de Inventario"; dominios = ("stock",)

    def responder(self, consulta, ctx, *, manager=None):
        emp = self._emp(ctx); st = self._prediccion().stock(emp)
        rot = next((p["valor"] for p in st.get("predicciones", []) if p["metrica"] == "rotura_stock"), 0)
        exc = next((p["valor"] for p in st.get("predicciones", []) if p["metrica"] == "sobrestock"), 0)
        base = self._ia(consulta, ctx)
        txt = f"Riesgo de rotura en {rot} articulos, {exc} con sobrestock. {base.get('texto', '')}".strip()
        return respuesta(self.nombre, txt, fuentes=["Inventario", "Kardex", "PredictionService"],
                         datos=st, predicciones=st.get("predicciones", []))


class AgenteFinanciero(Agente):
    nombre = "financiero"; titulo = "Agente Financiero"; dominios = ("tesoreria", "financiero")

    def responder(self, consulta, ctx, *, manager=None):
        emp = self._emp(ctx); te = self._prediccion().tesoreria(emp)
        pr = "; ".join(f"{p['metrica']}={p['valor']}" for p in te.get("predicciones", []))
        return respuesta(self.nombre, f"Tesoreria/finanzas: {pr}.",
                         fuentes=["Tesoreria", "Facturacion", "PredictionService"], datos=te,
                         predicciones=te.get("predicciones", []))


class AgenteRRHH(Agente):
    nombre = "rrhh"; titulo = "Agente RRHH"; dominios = ("rrhh",)

    def responder(self, consulta, ctx, *, manager=None):
        emp = self._emp(ctx); rr = self._prediccion().rrhh(emp)
        n = next((p["valor"] for p in rr.get("predicciones", []) if p["metrica"] == "contratos_por_vencer"), 0)
        # Enterprise 8 (SUBFASE 8.13): consulta el Gemelo Digital RRHH antes de responder.
        twin = self._twin(ctx) or {}
        ind = twin.get("indicadores", {})
        n = ind.get("contratos_por_vencer", n)
        extra = (f" Delegaciones activas: {ind.get('delegaciones_activas', 0)}; "
                 f"ausencias hoy: {ind.get('ausencias_hoy', 0)}.") if ind else ""
        return respuesta(self.nombre, f"RRHH: {n} contratos proximos a vencer; revisar cobertura.{extra}",
                         fuentes=["RRHH", "Gemelo Digital", "PredictionService"],
                         datos={"prediccion": rr, "gemelo": twin})


class AgenteFiscal(Agente):
    nombre = "fiscal"; titulo = "Agente Fiscal"; dominios = ("fiscal",)

    def responder(self, consulta, ctx, *, manager=None):
        info = ("Asesoramiento fiscal (solo informativo): IVA/IRPF/Verifactu/AEAT/Recargo de "
                "Equivalencia/Intracomunitarias. Nunca modifico declaraciones.")
        datos = {}
        try:
            import datetime as _dt
            from src.services.contabilidad import iva as IVA
            r = IVA.resumen_303(anio=_dt.date.today().year)
            info = (f"Borrador 303: devengado {r.get('iva_devengado_cuota')}, deducible "
                    f"{r.get('iva_deducible_cuota')}, resultado {r.get('resultado')} ({r.get('sentido')}). "
                    "Solo informativo.")
            datos = r
        except Exception:
            pass
        return respuesta(self.nombre, info, fuentes=["Contabilidad/IVA", "AEAT", "Verifactu"], datos=datos)


class AgenteLogistico(Agente):
    nombre = "logistico"; titulo = "Agente Logistico"; dominios = ("logistica",)

    def responder(self, consulta, ctx, *, manager=None):
        emp = self._emp(ctx)
        try:
            from src.services import actividad
            g = actividad.sincronizacion.infraestructura(emp).get("global", {})
        except Exception:
            g = {}
        base = self._ia(consulta, ctx)
        return respuesta(self.nombre, f"Logistica/almacenes/recepciones. {base.get('texto', '')}".strip(),
                         fuentes=["Logistica", "Kardex", "Sincronizacion Enterprise"],
                         datos={"infraestructura": g})


class AgenteTPV(Agente):
    nombre = "tpv"; titulo = "Agente TPV"; dominios = ("tpv",)

    def responder(self, consulta, ctx, *, manager=None):
        base = self._ia("ventas hoy", ctx)
        return respuesta(self.nombre, f"TPV — ventas/cajas/cierres del dia. {base.get('texto', '')}".strip(),
                         fuentes=["TPV", "Ventas", "IAService"], datos=base.get("datos"))


class AgenteAuditoria(Agente):
    nombre = "auditoria"; titulo = "Agente de Auditoria"; dominios = ("auditoria",)

    def responder(self, consulta, ctx, *, manager=None):
        emp = self._emp(ctx); pa = {}
        try:
            from src.services import automatizacion
            pa = automatizacion.panel.resumen(emp)
        except Exception:
            pass
        err = 0
        try:
            from src.services import actividad
            err = len([s for s in actividad.sincronizacion.sesiones(emp, 30)
                       if str(s.get("estado")).upper() == "ERROR"])
        except Exception:
            pass
        return respuesta(self.nombre, f"Auditoria: {pa.get('total', 0)} automatizaciones registradas, "
                         f"{err} sincronizaciones con error. Integridad y logs disponibles.",
                         fuentes=["Auditoria", "Workflow", "Automatizacion", "Sincronizacion"], datos=pa)


AGENTES = [AgenteComercial(), AgenteCompras(), AgenteInventario(), AgenteFinanciero(),
           AgenteRRHH(), AgenteFiscal(), AgenteLogistico(), AgenteTPV(), AgenteAuditoria()]
