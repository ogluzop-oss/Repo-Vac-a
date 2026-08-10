"""
GovernanceService (Paquete Enterprise 7) — fachada unica del gobierno corporativo. Coordina
organigrama, responsables, delegaciones, cadenas de aprobacion, escalado, autoridad, politicas y
el gobierno para la IA. NO duplica motores: reutiliza Workflow/AutomationService/Auditoria.
"""

from src.services.gobierno import (aprobaciones, autoridad, dashboard,
                                   delegacion, escalado, gobierno_ia,
                                   organigrama, politicas, responsables)


class GovernanceService:
    # Organigrama (7.1/7.6)
    def crear_nodo(self, *a, **k): return organigrama.crear_nodo(*a, **k)
    def mapa(self, id_empresa=None): return organigrama.mapa(id_empresa)
    def subarbol(self, id_nodo, id_empresa=None): return organigrama.subarbol(id_nodo, id_empresa)

    # Responsables (7.2)
    def asignar_responsable(self, *a, **k): return responsables.asignar(*a, **k)
    def cadena_mando(self, id_nodo, id_empresa=None): return responsables.cadena_mando(id_nodo, id_empresa)

    # Delegacion (7.4)
    def delegar(self, *a, **k): return delegacion.delegar(*a, **k)
    def delegaciones_activas(self, id_empresa=None): return delegacion.activas(id_empresa)

    # Aprobaciones (7.3)
    def cadena_aprobacion(self, entidad, importe=0, id_empresa=None):
        return aprobaciones.cadena_para(entidad, importe, id_empresa)
    def iniciar_aprobacion(self, *a, **k): return aprobaciones.iniciar_aprobacion(*a, **k)

    # Autoridad (7.7) / IA (7.9)
    def puede_aprobar(self, usuario, entidad, importe=0, id_empresa=None, perfil=None):
        return gobierno_ia.puede_aprobar(usuario, entidad, importe, id_empresa, perfil)
    def contexto_ia(self, usuario, id_empresa=None, perfil=None):
        return gobierno_ia.contexto(usuario, id_empresa, perfil)

    # Politicas (7.8)
    def set_politica(self, *a, **k): return politicas.set_politica(*a, **k)
    def politica(self, clave, id_nodo=None, id_empresa=None):
        return politicas.obtener(clave, id_nodo, id_empresa)

    # Escalado (7.5)
    def revisar_escalados(self, id_empresa=None): return escalado.revisar(id_empresa)

    # Dashboard directivo (7.10)
    def dashboard(self, id_empresa=None): return dashboard.indicadores(id_empresa)


_service = GovernanceService()


def servicio() -> GovernanceService:
    return _service
