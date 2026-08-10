"""
Global SaaS Platform (Fase VI · Bloque 13) — fachada.

Convierte Smart Manager AI en una plataforma SaaS MUNDIAL: multi-región (EU/AM/AS/AF/OC) con
resolución Region → Cluster → Node → Tenant, planes globales (Starter…Government), límites y consumo
por plan/empresa, Feature Flags Cloud (región/empresa/plan/usuario), configuración global y modelos
de despliegue (Cloud/On-Premise/Hybrid/Edge). REUTILIZA SaaS (licensing/planes/métricas/branding),
i18n y el Cloud (nodos/clusters/routing). Sin cobros. Multiempresa/multi-región.

    from src.services import saas_global as sg
    sg.planes_global.asignar_a_empresa(emp, "professional", region="eu")
    sg.regiones.resolver(emp)
    sg.feature_flags.activo("nueva_ui", id_empresa=emp)
"""

from src.services.saas_global import (  # noqa: F401
    configuracion_global, consumo, deployment, feature_flags, limites, planes_global, regiones,
)

__all__ = ["configuracion_global", "consumo", "deployment", "feature_flags", "limites",
           "planes_global", "regiones"]
