"""
DigitalTwinService (Paquete Enterprise 8, SUBFASE 8.1) — FACHADA PUBLICA UNICA del Gemelo Digital.

Toda consulta al estado global de la empresa DEBE pasar por aqui. IA, Copiloto y Agentes NUNCA
acceden a decenas de modulos directamente: preguntan al gemelo. El servicio coordina los estados
por dominio (empresa/inventario/comercial/rrhh/financiero/logistico), los mantiene en una cache
en proceso con TTL, y los refresca automaticamente cuando el Event Bus notifica un cambio
(invalidacion por eventos, SUBFASE 8.9/8.16). No duplica datos: cada estado se DERIVA de las
fuentes Enterprise existentes bajo demanda.
"""

import logging
import threading
import time

from src.services.gemelo import (comercial, consistencia, consultas, dashboard,
                                  dependencias, estado_global, financiero,
                                  fuentes, inventario, logistico, modelo, rrhh,
                                  snapshot)

logger = logging.getLogger("gemelo.motor")

# Dominio -> funcion que construye su estado vivo (todas reutilizan `fuentes`).
DOMINIOS = {
    "empresa": estado_global.estado,
    "inventario": inventario.estado,
    "comercial": comercial.estado,
    "rrhh": rrhh.estado,
    "financiero": financiero.estado,
    "logistico": logistico.estado,
}

_TTL = 30  # segundos: ventana de frescura entre eventos (el bus invalida antes si hay cambios)


class DigitalTwinService:
    def __init__(self):
        self._cache = {}          # (dominio, emp) -> (expira_ts, estado)
        self._lock = threading.RLock()
        self._suscrito = False

    # ── Suscripcion perezosa al Event Bus (idempotente) ──
    def _asegurar_suscripcion(self):
        if self._suscrito:
            return
        try:
            from src.services.gemelo import eventos_twin
            eventos_twin.suscribir()
        except Exception as e:
            logger.debug("suscripcion bus: %s", e)
        self._suscrito = True

    # ── Estado por dominio (cacheado, refrescado por eventos) ──
    def estado(self, dominio, id_empresa=None) -> dict:
        self._asegurar_suscripcion()
        emp = fuentes.emp(id_empresa)
        fn = DOMINIOS.get(dominio)
        if not fn:
            return {"dominio": dominio, "error": "dominio desconocido"}
        clave = (dominio, emp)
        with self._lock:
            hit = self._cache.get(clave)
            if hit and hit[0] > time.time():
                return hit[1]
        try:
            est = fn(emp)
        except Exception as e:
            logger.debug("estado %s: %s", dominio, e)
            est = modelo.estado_dominio(dominio, resumen="No disponible.")
        with self._lock:
            self._cache[clave] = (time.time() + _TTL, est)
        return est

    def estados(self, id_empresa=None) -> dict:
        """Estado de TODOS los dominios (para el dashboard y el resumen ejecutivo)."""
        return {d: self.estado(d, id_empresa) for d in DOMINIOS}

    def invalidar(self, dominios=None, id_empresa=None):
        """Invalida el estado cacheado (llamado por el Event Bus). None = todos los dominios."""
        emp = fuentes.emp(id_empresa)
        objetivo = set(dominios) if dominios else set(DOMINIOS)
        with self._lock:
            for d in objetivo:
                self._cache.pop((d, emp), None)

    # ── Resumen ejecutivo global (SUBFASE 8.2/8.10) ──
    def estado_global(self, id_empresa=None) -> dict:
        estados = self.estados(id_empresa)
        riesgo = modelo.peor_riesgo(*[e.get("riesgo", modelo.RIESGO_BAJO) for e in estados.values()])
        alertas = []
        for e in estados.values():
            alertas += [{"dominio": e.get("dominio"), "texto": a} for a in e.get("alertas", [])]
        partes = [estados["empresa"].get("resumen", "")]
        for d in ("inventario", "comercial", "financiero", "rrhh", "logistico"):
            r = estados.get(d, {}).get("resumen")
            if r:
                partes.append(f"[{d}] {r}")
        return {
            "id_empresa": fuentes.emp(id_empresa),
            "riesgo_global": riesgo,
            "resumen": estados["empresa"].get("resumen", ""),
            "texto": " ".join(partes),
            "dominios": estados,
            "alertas": alertas,
        }

    # ── Consultas instantaneas (SUBFASE 8.10) ──
    def estado_empresa(self, id_empresa=None):       return self.estado_global(id_empresa)
    def estado_tienda(self, nombre, id_empresa=None): return consultas.estado_tienda(nombre, id_empresa)
    def procesos_abiertos(self, id_empresa=None):     return consultas.procesos_abiertos(id_empresa)
    def recursos_bloqueados(self, id_empresa=None):   return consultas.recursos_bloqueados(id_empresa)
    def contratos_por_vencer(self, id_empresa=None, dias=30):
        return consultas.contratos_por_vencer(id_empresa, dias=dias)
    def pedidos_pendientes(self, id_empresa=None):    return consultas.pedidos_pendientes(id_empresa)
    def almacenes_con_incidencias(self, id_empresa=None):
        return consultas.almacenes_con_incidencias(id_empresa)

    # ── Contexto de un dominio para Agentes/IA (SUBFASE 8.11/8.13) ──
    def contexto_dominio(self, dominio, id_empresa=None) -> dict:
        mapa = {"ventas": "comercial", "crm": "comercial", "comercial": "comercial",
                "stock": "inventario", "inventario": "inventario", "compras": "logistico",
                "logistica": "logistico", "logistico": "logistico", "tesoreria": "financiero",
                "financiero": "financiero", "rrhh": "rrhh", "empresa": "empresa"}
        return self.estado(mapa.get(dominio, "empresa"), id_empresa)

    # ── Dependencias (SUBFASE 8.8) ──
    def registrar_dependencia(self, *a, **k): return dependencias.registrar(*a, **k)
    def dependencias(self, entidad, entidad_id, id_empresa=None):
        return dependencias.cadena(entidad, entidad_id, id_empresa=id_empresa)

    # ── Dashboard (SUBFASE 8.14) ──
    def dashboard(self, id_empresa=None): return dashboard.panel(id_empresa)

    # ── Consistencia (SUBFASE 8.15) ──
    def verificar_consistencia(self, id_empresa=None, resincronizar=True):
        return consistencia.verificar(id_empresa, resincronizar=resincronizar)
    def incoherencias(self, id_empresa=None): return consistencia.abiertas(id_empresa)

    # ── Snapshot materializado ──
    def snapshot(self, id_empresa=None) -> bool:
        g = self.estado_global(id_empresa)
        return snapshot.guardar(id_empresa, estado=g, riesgo=g.get("riesgo_global", "BAJO"))
    def ultimo_snapshot(self, id_empresa=None): return snapshot.ultimo(id_empresa)


_service = DigitalTwinService()


def servicio() -> DigitalTwinService:
    return _service
