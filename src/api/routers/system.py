"""Router /system — salud y versión (público) + estado operacional unificado (autenticado, F2)."""

from src.api.security import requiere_auth

# Capacidades móviles finas que SÍ dependen del rol/permisos del usuario (más allá de la edición): el
# resto del catálogo de `mobile_client/src/api/capabilities.ts` es base (visible para cualquier rol,
# igual que hoy) — solo estas dos exigen un permiso RBAC concreto, mismo criterio que su equivalente de
# escritorio (`logistica.traspasos` migrado del check ad-hoc de `gui/recepcion_pale.py`;
# `etiquetas.precio.editar` nuevo, para la pestaña de cambiar precio del móvil).
_PERMISO_POR_CAPACIDAD_FINA = {
    "logistica.traspaso": "logistica.traspasos",
    "etiquetas.precio": "etiquetas.precio.editar",
}


def registrar(bp):
    @bp.get("/system/health")
    def health():
        from flask import jsonify
        estado = {"status": "ok"}
        try:
            from src.services.observabilidad import health as H
            if hasattr(H, "estado"):
                estado = H.estado()
            elif hasattr(H, "salud"):
                estado = H.salud()
        except Exception:
            pass
        return jsonify(estado)

    @bp.get("/system/version")
    def version():
        from flask import jsonify
        return jsonify({"name": "Smart Manager AI", "api": "v1", "plataforma": "Enterprise"})

    # Edición/vertical de ESTA instalación (SUPERMARKET/RETAIL/PHARMACY/TEXTIL/BAKERY) + qué
    # capacidades móviles corresponden — mismo motor que ya gatea escritorio (`services.verticales`,
    # sin duplicar reglas). Público: no es información sensible, es "qué tipo de negocio es esto",
    # necesaria para que el móvil arme su catálogo de módulos ANTES incluso de hacer login.
    @bp.get("/system/edition")
    def edition():
        from flask import jsonify
        from src.services import verticales
        from src.services.mobile import core as mobile_core
        return jsonify({
            "edicion": verticales.vertical_actual(),
            "capacidades_visibles": mobile_core.capacidades_visibles(),
        })

    # ── Health checks estándar de orquestador (Fase cloud): liveness / readiness / version. PÚBLICOS,
    #    sin información sensible, reutilizan observabilidad.health (NO crea mecanismos nuevos). El código
    #    HTTP permite a un balanceador/orquestador (k8s, LB) decidir tráfico: 200=ok, 503=no listo. ──
    @bp.get("/health/live")
    def health_live():
        from flask import jsonify
        try:
            from src.services.observabilidad import health as H
            r = H.live()
        except Exception:
            r = {"status": "ok"}
        return jsonify(r), 200   # liveness: si el proceso responde, está vivo

    @bp.get("/health/ready")
    def health_ready():
        from flask import jsonify
        try:
            from src.services.observabilidad import health as H
            r = H.ready()
        except Exception:
            r = {"status": "unavailable"}
        return jsonify(r), (200 if r.get("status") == "ok" else 503)

    @bp.get("/health/version")
    def health_version():
        from flask import jsonify
        return jsonify({"name": "Smart Manager AI", "api": "v1"})

    # Capacidades EFECTIVAS del usuario autenticado (rol base + permisos individuales), para que el
    # móvil oculte/muestre módulos/pestañas igual que lo haría el rol en escritorio — sin duplicar el
    # motor RBAC (delega en `services.autorizacion.puede`, que YA respeta concesiones individuales vía
    # `usuarios_permisos`). Distinto de `/system/edition` (público, por instalación): este es privado y
    # por usuario.
    @bp.get("/me/modules")
    @requiere_auth()
    def mis_modulos():
        from flask import g, jsonify
        from src.services import autorizacion
        usuario = g.ctx["usuario"]
        emp = g.ctx["id_empresa"]
        # Capacidades base del catálogo móvil: visibles para cualquier rol (no se pide restringirlas).
        modulos = {k: True for k in (
            "stock", "mermas", "logistica", "ubicacion", "etiquetas", "distribucion",
            "gmao", "calidad", "sat", "transporte", "obrador", "mrp",
        )}
        for clave, permiso in _PERMISO_POR_CAPACIDAD_FINA.items():
            modulos[clave] = autorizacion.puede(usuario, permiso, id_empresa=emp)
        return jsonify(modulos)

    # ── Estado operacional unificado (F2): reutiliza observabilidad.estado. Autenticado; el tenant
    #    sale SIEMPRE del token (aislamiento). No crea mecanismos nuevos: compone los existentes. ──
    @bp.get("/system/status")
    @requiere_auth()
    def status():
        from flask import g, jsonify
        from src.services.observabilidad import estado
        return jsonify({"global": estado.global_(),
                        "modulos": estado.por_modulo(g.ctx["id_empresa"])})

    @bp.get("/system/status/tenant")
    @requiere_auth()
    def status_tenant():
        from flask import g, jsonify
        from src.services.observabilidad import estado
        return jsonify(estado.por_tenant(g.ctx["id_empresa"]))

    @bp.get("/system/selftest")
    @requiere_auth()
    def selftest():
        from flask import g, jsonify
        from src.services.observabilidad import estado
        r = estado.self_test(g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 503)

    @bp.get("/system/diagnostico")
    @requiere_auth()
    def diagnostico():
        from flask import g, jsonify
        from src.services.observabilidad import estado
        return jsonify(estado.diagnostico(g.ctx["id_empresa"]))
