"""
Router /commerce (Plataforma de Comercio Digital · Fase 1 · scaffolding) — reutiliza la seguridad
Enterprise (JWT/API Key + tenant + RBAC + rate limit vía `requiere_auth`). Cablea la superficie REST
de la PCD; delega SIEMPRE en el servicio `comercio_digital` (nunca BD directa). En Fase 1 solo expone
descriptor/health; los recursos funcionales se añaden en sus fases (RFC-CD-006).
"""

from src.api.security import requiere_auth


def _observar():
    """Observabilidad (Fase 9): registra el acceso a la superficie de comercio. No bloquea. La
    autorización RBAC ya la aplica `requiere_auth('comercio.ver')`; los límites SaaS (cuotas) se
    aplican en los puntos de CREACIÓN, no en la lectura."""
    try:
        from src.services.comercio_digital import gobernanza
        gobernanza.metrica("commerce_rest_hit")
    except Exception:
        pass


def registrar(bp):
    @bp.get("/commerce")
    @requiere_auth("comercio.ver")
    def commerce_descriptor():
        from flask import jsonify
        _observar()
        from src.services import comercio_digital as cd
        return jsonify(cd.descriptor())

    @bp.get("/commerce/health")
    @requiere_auth("comercio.ver")
    def commerce_health():
        from flask import jsonify
        _observar()
        from src.services import comercio_digital as cd
        d = cd.descriptor()
        return jsonify({"status": "ok", "fase": d.get("fase"), "estado": d.get("estado"),
                        "subservicios": list((d.get("subservicios") or {}).keys())})
