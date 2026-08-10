"""
Motor central de prediccion (Paquete Enterprise 3, SUBFASE 3.1) — `PredictionService`, punto
UNICO de entrada. Toda prediccion futura pasa por aqui; nunca se llaman los dominios internos ni
el ERP directamente. Solo LEE/analiza/predice/recomienda; nunca ejecuta ni escribe (SUBFASE 3.2+
delegan la ejecucion a Workflow/BPM/usuario). Multiempresa/multitienda. ML-ready (heuristicas).
"""

import logging

from src.services.prediccion import (clientes, compras, configuracion,
                                     indicadores, produccion, rrhh, riesgos,
                                     stock, tesoreria, ventas)

logger = logging.getLogger("prediccion.motor")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


class PredictionService:
    """Fachada unica del motor predictivo. Desacoplada, read-only, multiempresa."""

    # ── Dominios (SUBFASE 3.2-3.7) ──
    def stock(self, id_empresa=None):
        return stock.predecir(id_empresa)

    def ventas(self, id_empresa=None):
        return ventas.predecir(id_empresa)

    def compras(self, id_empresa=None):
        return compras.predecir(id_empresa)

    def tesoreria(self, id_empresa=None):
        return tesoreria.predecir(id_empresa)

    def rrhh(self, id_empresa=None):
        return rrhh.predecir(id_empresa)

    def clientes(self, id_empresa=None):
        return clientes.predecir(id_empresa)

    def produccion(self, id_empresa=None):
        return produccion.predecir(id_empresa)

    def documental(self, id_empresa=None):
        from src.services.ia import documental as _doc
        return _doc.analizar(id_empresa)

    # ── Transversales (SUBFASE 3.8/3.9/3.11) ──
    def riesgos(self, id_empresa=None):
        return riesgos.indice(id_empresa)

    def oportunidades(self, id_empresa=None):
        return indicadores.oportunidades(id_empresa)

    # ── Forecasting UNIFICADO (Fase 5): calidad → selección → backtest → Prophet/estadística/heurística,
    #    con explicabilidad honesta y evento Event Bus. Delega en `prediccion.forecasting` (mismo motor,
    #    no paralelo). Aislado por tenant. ──
    def forecast_ventas(self, id_empresa=None, *, horizonte=7):
        from src.services.prediccion import forecasting
        return forecasting.predecir_ventas(id_empresa, horizonte=horizonte)

    def _dominios(self, id_empresa=None):
        return [self.stock(id_empresa), self.ventas(id_empresa), self.compras(id_empresa),
                self.tesoreria(id_empresa), self.rrhh(id_empresa), self.clientes(id_empresa),
                self.produccion(id_empresa), self.documental(id_empresa)]

    def alertas(self, id_empresa=None) -> list:
        out = []
        for d in self._dominios(id_empresa):
            out += d.get("alertas", [])
        return out

    def predicciones(self, id_empresa=None) -> list:
        out = []
        for d in self._dominios(id_empresa):
            for p in d.get("predicciones", []):
                out.append({**p, "dominio": d.get("dominio")})
        return out

    def recomendaciones(self, id_empresa=None) -> list:
        out = []
        for d in (self.compras(id_empresa), self.clientes(id_empresa)):
            out += d.get("recomendaciones", [])
        return out

    def tendencias(self, id_empresa=None) -> dict:
        v = self.ventas(id_empresa)
        s = self.stock(id_empresa)
        return {"ventas": v.get("tendencia"), "demanda": s.get("tendencia_demanda")}

    # ── Dashboard predictivo (SUBFASE 3.11) ──
    def panel_predictivo(self, id_empresa=None) -> dict:
        emp = _emp(id_empresa)
        return {
            "riesgos": self.riesgos(emp),
            "predicciones": self.predicciones(emp),
            "tendencias": self.tendencias(emp),
            "oportunidades": self.oportunidades(emp),
            "alertas": self.alertas(emp),
            "recomendaciones": self.recomendaciones(emp),
            "titulares": indicadores.titulares(emp),
        }

    # ── Consulta de futuro (la usa IAService, SUBFASE 3.12) ──
    def responder_futuro(self, texto, id_empresa=None) -> dict:
        t = (texto or "").lower()
        if any(k in t for k in ("rotura", "sin stock", "agotar", "agotara")):
            s = self.stock(id_empresa)
            n = next((p["valor"] for p in s.get("predicciones", []) if p["metrica"] == "rotura_stock"), 0)
            return {"intent": "rotura", "texto": f"Se preven roturas en {n} articulos la proxima semana.",
                    "datos": s}
        if any(k in t for k in ("proveedor", "compra")):
            return {"intent": "compras", "texto": "Recomendaciones de compra generadas.",
                    "datos": self.compras(id_empresa)}
        if any(k in t for k in ("impago", "liquidez", "tesoreria", "cobr")):
            return {"intent": "tesoreria", "texto": "Analisis de tesoreria predictiva.",
                    "datos": self.tesoreria(id_empresa)}
        if any(k in t for k in ("riesgo", "problema")):
            r = self.riesgos(id_empresa)
            emp = next((x for x in r if x["entidad"] == "empresa"), {})
            return {"intent": "riesgos", "texto": f"Riesgo global: {emp.get('nivel', 'bajo')} "
                    f"(score {emp.get('score', 0)}).", "datos": r}
        # Por defecto: prevision de ventas.
        v = self.ventas(id_empresa)
        pr = {p["horizonte"]: p["valor"] for p in v.get("predicciones", [])}
        return {"intent": "ventas", "texto": f"Prevision de ventas — proxima semana: "
                f"{pr.get('proxima semana', 0)}; proximo mes: {pr.get('proximo mes', 0)}.", "datos": v}

    def configuracion(self, id_empresa=None):
        return configuracion.estado(id_empresa)


_service = PredictionService()


def servicio() -> PredictionService:
    return _service
