"""
Puente INTERNO entre el sitio oficial público (`src.backend.sitio_oficial`, dominio comercial
`smartmanager-app.com`) y la BD CENTRAL de licencias. Mismo motivo que el resto de
`backend_central/`: el sitio oficial corre en el contenedor `backend` (conectado a
`smart_manager_db`, la BD local/multiempresa), nunca a `smart_manager_central` directamente — así
que necesita cruzar al contenedor `backend_central` por HTTP, dentro de la red privada de Docker
(nunca expuesto tal cual a Internet: Caddy solo publica `/central/*` en `admin.smartmanager-app.com`,
y estos endpoints concretos exigen además la cabecera `X-Internal-Secret`, ver `_requiere_secreto`).

Reutiliza TAL CUAL: `db.empresa.crear_empresa` (alta de empresa central), `services.saas.suscripciones`
(estado/alta de suscripción) y el mismo campo `codigos_activacion` que ya consume `rutas_licencia.py`
en el otro sentido (canje, no generación). Las contraseñas de `cuentas_web_central` usan PBKDF2
(`werkzeug.security`), NUNCA el hash SHA-256 sin sal de `db/usuario.py` (sistema de identidad
distinto: empleados del ERP de un cliente vs. clientes del propio sitio comercial).
"""

import logging
import os
import random
import string

logger = logging.getLogger("backend_central.rutas_sitio_web")


def _secreto_interno() -> str:
    return os.getenv("CENTRAL_INTERNAL_SECRET", "")


def _requiere_secreto(request):
    """True si la petición trae el secreto compartido correcto. Sin `CENTRAL_INTERNAL_SECRET`
    configurado, se rechaza SIEMPRE (nunca un bypass por falta de configuración)."""
    esperado = _secreto_interno()
    recibido = request.headers.get("X-Internal-Secret", "")
    return bool(esperado) and recibido == esperado


def _generar_codigo() -> str:
    grupo = lambda: "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"SM-{grupo()}-{grupo()}-{grupo()}"


def _fila(cur, r):
    return r if isinstance(r, dict) else (dict(zip([d[0] for d in cur.description], r)) if r else None)


def crear_blueprint():
    from flask import Blueprint, jsonify, request

    bp = Blueprint("sitio_web_central", __name__, url_prefix="/central/sitio")

    @bp.before_request
    def _gate():
        if not _requiere_secreto(request):
            return jsonify({"ok": False, "error": "No autorizado."}), 403

    @bp.post("/registrar_gratis")
    def registrar_gratis():
        """Alta directa SIN pago, para cuando el plan BASIC tenga precio 0 (hoy no: BASIC cuesta
        29€/mes, ver `services.saas.planes.PLANES['BASIC']` — `sitio_oficial.py` solo llama a este
        endpoint si el precio del plan es exactamente 0, así que con la tarificación actual queda
        sin uso, pero se conserva lista para un futuro plan gratuito): empresa + cuenta web +
        código de activación, los tres en el mismo paso."""
        datos = request.get_json(silent=True) or {}
        nombre_empresa = (datos.get("nombre_empresa") or "").strip()
        email = (datos.get("email") or "").strip().lower()
        password_hash = datos.get("password_hash") or ""
        if not nombre_empresa or not email or not password_hash:
            return jsonify({"ok": False, "error": "Faltan datos obligatorios."}), 400

        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM cuentas_web_central WHERE email=%s", (email,))
            if cur.fetchone():
                return jsonify({"ok": False, "error": "Ya existe una cuenta con ese email."}), 409

        from src.db.empresa import crear_empresa
        id_empresa_central = crear_empresa(nombre_empresa)
        if not id_empresa_central:
            return jsonify({"ok": False, "error": "No se pudo registrar la empresa."}), 500

        from src.services.saas import suscripciones as S
        S.crear(id_empresa_central, "BASIC", prueba=False)

        codigo = _generar_codigo()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cuentas_web_central (email, password_hash, id_empresa_central) "
                "VALUES (%s,%s,%s)", (email, password_hash, id_empresa_central))
            cur.execute(
                "INSERT INTO codigos_activacion (codigo, plan, email_cliente) VALUES (%s,%s,%s)",
                (codigo, "BASIC", email))
            conn.commit()

        logger.info("Alta BASIC gratuita vía sitio oficial: empresa=%s email=%s",
                   id_empresa_central, email)
        return jsonify({"ok": True, "codigo": codigo, "plan": "BASIC"})

    @bp.post("/preregistrar")
    def preregistrar():
        """Paso 1 del alta de pago (cualquier plan con precio > 0 — hoy los 3): valida que el email
        no exista ya, pero NO crea nada todavía — la empresa/cuenta/código solo se crean tras
        confirmar el pago real (`/confirmar_pago`), para no dejar empresas huérfanas de un checkout
        abandonado."""
        datos = request.get_json(silent=True) or {}
        email = (datos.get("email") or "").strip().lower()
        if not email:
            return jsonify({"ok": False, "error": "Falta el email."}), 400
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM cuentas_web_central WHERE email=%s", (email,))
            if cur.fetchone():
                return jsonify({"ok": False, "error": "Ya existe una cuenta con ese email."}), 409
        return jsonify({"ok": True})

    @bp.post("/confirmar_pago")
    def confirmar_pago():
        """Tras un Stripe Checkout con `payment_status=paid` (verificado por quien llama: la propia
        página de éxito del sitio oficial, o el webhook — ambos verifican contra la API de Stripe
        antes de llamar aquí, esto NO vuelve a comprobarlo). Idempotente por `session_id`: si ya se
        generó un código para esa sesión, lo devuelve tal cual en vez de duplicar."""
        datos = request.get_json(silent=True) or {}
        session_id = (datos.get("session_id") or "").strip()
        plan = (datos.get("plan") or "").strip().upper()
        email = (datos.get("email") or "").strip().lower()
        nombre_empresa = (datos.get("nombre_empresa") or "").strip()
        password_hash = datos.get("password_hash") or ""
        stripe_customer_id = datos.get("stripe_customer_id")
        from src.services.saas import planes as _P_check
        if not session_id or not _P_check.plan(plan) or not email or not nombre_empresa:
            return jsonify({"ok": False, "error": "Faltan datos obligatorios."}), 400

        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, plan FROM codigos_activacion WHERE stripe_session_id=%s",
                        (session_id,))
            existente = _fila(cur, cur.fetchone())
            if existente:
                return jsonify({"ok": True, "codigo": existente["codigo"], "plan": existente["plan"],
                                "ya_existia": True})

            cur.execute("SELECT id, id_empresa_central FROM cuentas_web_central WHERE email=%s",
                        (email,))
            cuenta = _fila(cur, cur.fetchone())

        if cuenta:
            id_empresa_central = cuenta["id_empresa_central"]
        else:
            from src.db.empresa import crear_empresa
            id_empresa_central = crear_empresa(nombre_empresa)
            if not id_empresa_central:
                return jsonify({"ok": False, "error": "No se pudo registrar la empresa."}), 500
            if not password_hash:
                return jsonify({"ok": False, "error": "Falta la contraseña para la cuenta nueva."}), 400
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO cuentas_web_central (email, password_hash, id_empresa_central) "
                    "VALUES (%s,%s,%s)", (email, password_hash, id_empresa_central))
                conn.commit()

        from src.services.saas import licensing as _L
        from src.services.saas import planes as _P
        from src.services.saas import suscripciones as S

        # `S.crear(..., prueba=False)` facturaría INTERNAMENTE vía el proveedor de cobro recurrente
        # (SEPA, `billing/stripe_gateway.py`) — redundante y erróneo aquí: el cobro del primer mes
        # YA lo hizo Stripe Checkout (tarjeta, confirmado por quien llama a este endpoint). Se crea
        # la suscripción sin disparar ese cobro (`prueba=True`) y se activa + factura a mano,
        # reflejando el pago REAL ya ocurrido — el cobro recurrente interno queda para las
        # RENOVACIONES futuras de este mismo plan.
        sid = S.crear(id_empresa_central, plan, prueba=True, dias_prueba=30)
        if sid:
            precio = float(_P.plan(plan)["precio"])
            import datetime as _dt
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE suscripciones SET estado='activa' WHERE id=%s", (sid,))
                cur.execute(
                    "INSERT INTO facturas_saas (id_empresa, id_suscripcion, numero, importe, "
                    "estado, fecha, concepto) VALUES (%s,%s,%s,%s,'pagada',%s,'suscripcion')",
                    (id_empresa_central, sid, f"SAAS-{session_id[:20].upper()}", precio,
                     _dt.date.today()))
                fid = cur.lastrowid
                cur.execute(
                    "INSERT INTO pagos_saas (id_empresa, id_factura, proveedor, importe, estado, "
                    "ref_externa, intentos) VALUES (%s,%s,'stripe_checkout',%s,'pagado',%s,1)",
                    (id_empresa_central, fid, precio, session_id))
                conn.commit()
            _L.asignar_plan(id_empresa_central, plan, estado="activa")

        if stripe_customer_id:
            # Vincula el customer de Stripe a la suscripción recién creada para que el webhook de
            # renovaciones (`backend_central.rutas_stripe`) pueda resolver la empresa en cobros futuros.
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT id FROM suscripciones WHERE id_empresa=%s ORDER BY id DESC LIMIT 1",
                            (id_empresa_central,))
                sus = _fila(cur, cur.fetchone())
                if sus:
                    cur.execute("UPDATE suscripciones SET stripe_customer_id=%s WHERE id=%s",
                                (stripe_customer_id, sus["id"]))
                    conn.commit()

        codigo = _generar_codigo()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO codigos_activacion (codigo, plan, email_cliente, stripe_session_id) "
                "VALUES (%s,%s,%s,%s)", (codigo, plan, email, session_id))
            conn.commit()

        logger.info("Alta %s vía Stripe Checkout: empresa=%s email=%s session=%s",
                   plan, id_empresa_central, email, session_id)
        return jsonify({"ok": True, "codigo": codigo, "plan": plan, "ya_existia": False})

    @bp.post("/login")
    def login():
        """Verifica email+contraseña contra `cuentas_web_central` (PBKDF2). Devuelve los datos
        mínimos para que el sitio oficial abra su propia sesión (cookie firmada) — el hash NUNCA
        sale de aquí."""
        from werkzeug.security import check_password_hash
        datos = request.get_json(silent=True) or {}
        email = (datos.get("email") or "").strip().lower()
        password = datos.get("password") or ""
        if not email or not password:
            return jsonify({"ok": False, "error": "Faltan credenciales."}), 400

        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, password_hash, id_empresa_central FROM cuentas_web_central "
                       "WHERE email=%s", (email,))
            cuenta = _fila(cur, cur.fetchone())
        if not cuenta or not check_password_hash(cuenta["password_hash"], password):
            return jsonify({"ok": False, "error": "Email o contraseña incorrectos."}), 401

        return jsonify({"ok": True, "id_empresa_central": cuenta["id_empresa_central"]})

    @bp.get("/mi_cuenta/<id_empresa_central>")
    def mi_cuenta(id_empresa_central):
        """Códigos emitidos + estado de suscripción de esta empresa central — para la página
        "Mi cuenta"/descargas del sitio oficial tras iniciar sesión."""
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, plan, usado, generado_en FROM codigos_activacion "
                "WHERE id_empresa_creada=%s OR email_cliente IN "
                "(SELECT email FROM cuentas_web_central WHERE id_empresa_central=%s) "
                "ORDER BY generado_en DESC", (id_empresa_central, id_empresa_central))
            cols = [d[0] for d in cur.description]
            codigos = [dict(zip(cols, r)) if not isinstance(r, dict) else r for r in cur.fetchall()]

        from src.services.saas import suscripciones as S
        estado = S.estado(id_empresa_central)
        for c in codigos:
            if c.get("generado_en"):
                c["generado_en"] = str(c["generado_en"])
        return jsonify({"ok": True, "codigos": codigos, "suscripcion": estado})

    return bp
