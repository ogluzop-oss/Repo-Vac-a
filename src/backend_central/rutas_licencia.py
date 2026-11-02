"""
Rutas del servidor CENTRAL de licencias: activación (canje de un código de un solo uso por
credenciales M2M propias de la instalación) y verificación periódica ("llamar a casa").

Reutiliza `services.saas.suscripciones` (ciclo de vida de la suscripción, ya existente),
`services.api_publica.developer`/`oauth` (alta y verificación de credenciales client-credentials,
ya existente) y `db.empresa.crear_empresa` (alta de empresa EN LA BD CENTRAL — sin relación con el
`id_empresa` de la BD local de ningún cliente). No se inventa ningún motor nuevo.
"""

import logging

logger = logging.getLogger("backend_central.rutas_licencia")


def crear_blueprint():
    from flask import Blueprint, jsonify, request

    bp = Blueprint("licencia_central", __name__, url_prefix="/central")

    @bp.post("/activar")
    def activar():
        """Canjea un código de activación de un solo uso por credenciales M2M para ESTA
        instalación. Idempotente por `installation_id`: si ya estaba activada, rechaza en vez de
        crear una segunda empresa central duplicada."""
        datos = request.get_json(silent=True) or {}
        codigo = (datos.get("codigo_activacion") or "").strip().upper()
        installation_id = (datos.get("installation_id") or "").strip()
        nombre_empresa = (datos.get("nombre_empresa") or "").strip()
        if not codigo or not installation_id or not nombre_empresa:
            return jsonify({"ok": False,
                            "error": "Faltan datos (código de activación, installation_id o nombre de empresa)."}), 400

        from src.db.conexion import obtener_conexion

        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, plan, usado FROM codigos_activacion WHERE codigo=%s", (codigo,))
            fila = cur.fetchone()
        if not fila:
            return jsonify({"ok": False, "error": "Código de activación no reconocido."}), 404
        id_codigo, plan, usado = (fila["id"], fila["plan"], fila["usado"]) if isinstance(fila, dict) else fila
        if usado:
            return jsonify({"ok": False, "error": "Este código de activación ya se ha usado."}), 409

        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM instalaciones_centrales WHERE installation_id=%s", (installation_id,)
            )
            if cur.fetchone():
                return jsonify({"ok": False, "error": "Esta instalación ya está activada."}), 409

        from src.db.empresa import crear_empresa
        id_empresa_central = crear_empresa(nombre_empresa)
        if not id_empresa_central:
            return jsonify({"ok": False, "error": "No se pudo registrar la empresa."}), 500

        from src.services.saas import suscripciones as S
        S.crear(id_empresa_central, plan, prueba=False)

        from src.services.api_publica import developer
        app_reg = developer.registrar_app(
            nombre_empresa, id_empresa=id_empresa_central,
            scopes=["licencia:verificar"], sandbox=False,
        )
        if not app_reg.get("ok"):
            return jsonify({"ok": False, "error": "No se pudo generar la credencial de la instalación."}), 500

        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO instalaciones_centrales (installation_id, id_empresa_central, "
                "nombre_empresa, client_id) VALUES (%s,%s,%s,%s)",
                (installation_id, id_empresa_central, nombre_empresa, app_reg["client_id"]),
            )
            cur.execute(
                "UPDATE codigos_activacion SET usado=1, usado_en=NOW(), id_empresa_creada=%s WHERE id=%s",
                (id_empresa_central, id_codigo),
            )
            conn.commit()

        logger.info("Instalación activada: %s (empresa central %s, plan %s)",
                   installation_id, id_empresa_central, plan)
        return jsonify({"ok": True, "client_id": app_reg["client_id"], "client_secret": app_reg["client_secret"]})

    @bp.post("/oauth/token")
    def token():
        """Client-credentials estándar (reutiliza `services.api_publica.oauth`, no un segundo
        sistema de tokens): la instalación cambia su `client_id`/`client_secret` por un JWT de
        corta duración para llamar a `/central/licencia/verificar`."""
        datos = request.get_json(silent=True) or {}
        client_id = datos.get("client_id")
        client_secret = datos.get("client_secret")
        if not client_id or not client_secret:
            return jsonify({"ok": False, "error": "Faltan credenciales."}), 400
        from src.services.api_publica import oauth
        r = oauth.emitir_token(client_id, client_secret, scopes=["licencia:verificar"])
        if not r:
            return jsonify({"ok": False, "error": "Credenciales inválidas."}), 401
        return jsonify({"ok": True, **r})

    @bp.get("/licencia/verificar")
    def verificar():
        """Llamada periódica ('llamar a casa'). Devuelve el estado REAL de la suscripción desde
        la BD central; el cliente de escritorio (Fase 3) es quien decide qué hacer con la
        respuesta — aquí solo se informa, nunca se actúa sobre la instalación del cliente."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"ok": False, "error": "Falta token de autorización."}), 401
        token_str = auth[len("Bearer "):]

        from src.services.api_publica import oauth
        if not oauth.verificar_scope(token_str, "licencia:verificar"):
            return jsonify({"ok": False, "error": "Token inválido o sin permiso."}), 403

        from src.seguridad import tokens as _tok
        claims = _tok.verificar(token_str, "access") or {}
        id_empresa_central = claims.get("empresa")
        if not id_empresa_central:
            return jsonify({"ok": False, "error": "Token sin empresa asociada."}), 403

        from src.services.saas import suscripciones as S
        sus = S.estado(id_empresa_central)
        if not sus:
            return jsonify({"ok": False, "error": "Esta instalación no tiene ninguna suscripción."}), 404

        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE instalaciones_centrales SET ultima_verificacion=NOW() WHERE id_empresa_central=%s",
                (id_empresa_central,),
            )
            conn.commit()

        return jsonify({
            "ok": True,
            "plan": sus.get("codigo_plan"),
            "estado": sus.get("estado"),
            "proximo_cobro": str(sus.get("proximo_cobro")) if sus.get("proximo_cobro") else None,
        })

    return bp
