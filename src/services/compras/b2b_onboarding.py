"""
Secuencia de onboarding comercial del Portal B2B (petición explícita, 2026-11-16; REPROPUESTA
2026-11-27 tras retirar la comisión del 2,5% — ver `comisiones_b2b.PCT_SIN_SUSCRIPCION = 0.0`): a
los pocos días de registrarse públicamente (`b2b_sesion_empresa.registrar_publico`), si la empresa
SIGUE en el plan Freemium del portal (sin ERP ni Plan de Pago del Portal — ver
`services.portal_plan.tier_efectivo`), se le envía UN ÚNICO correo comercial señalando el Plan de
Pago del Portal (sin límites de uso) y Smart Manager ERP (acceso completo + TPV/stock/RRHH/
facturación) — ya NO habla de ninguna comisión, retirada por completo para todos.

Reutiliza, sin motor nuevo:
- El mismo envío SMTP directo que `sitio_oficial._enviar_codigo_por_email` (mismo criterio: sin
  `SMTP_HOST` configurado, degrada honestamente y nunca bloquea nada — ni siquiera marca el envío,
  así que se reintenta en el siguiente barrido una vez se configure).
- `services.portal_plan.tier_efectivo`/`precio_mensual_portal` para no ofrecer lo que la empresa
  ya tiene y mostrar el precio real calculado (nunca inventado en el texto del correo).
- `portal_i18n.url_sitio_oficial` para el enlace de contratación, con el mismo patrón `?email=&
  origen=` ya usado por el banner comercial del dashboard (`portal_empresa_b2b.
  _banner_gancho_comercial_html`).

Disparo: `POST /jobs/b2b/onboarding` (`src.backend.rutas_jobs_b2b`), protegido por secreto
compartido (`B2B_JOBS_SECRET`) — vive en el proceso `backend` (dueño de la base compartida del
Portal B2B), no en `backend_central` (ese es para facturación SaaS). Se dispara desde un cron
EXTERNO del VPS, no desde el Scheduler de escritorio (esto no es un job por tenant).

Idempotente por `b2b_empresas_credenciales.onboarding_email_enviado_en` (migr. 0346): un barrido
repetido el mismo día no reenvía nada.
"""

import datetime as _dt
import logging
import os

from src.db.conexion import obtener_conexion

logger = logging.getLogger("compras.b2b_onboarding")

DIAS_ESPERA = 3


def candidatos(hoy=None) -> list[dict]:
    """Empresas registradas públicamente hace >= DIAS_ESPERA días, sin el correo enviado todavía."""
    hoy = hoy or _dt.date.today()
    limite = hoy - _dt.timedelta(days=DIAS_ESPERA)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT c.id, c.id_empresa, c.email_login, e.nombre_empresa FROM "
                "b2b_empresas_credenciales c JOIN empresas e ON e.id_empresa=c.id_empresa "
                "WHERE c.fecha_alta <= %s AND c.onboarding_email_enviado_en IS NULL",
                (limite,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error("candidatos: %s", e)
        return []


def _enviar_email(email_login, nombre_empresa) -> bool:
    host = os.environ.get("SMTP_HOST")
    if not host:
        logger.info("SMTP no configurado: no se envía onboarding B2B a %s (se reintentará).",
                   email_login)
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from urllib.parse import quote

        from src.backend.portal_i18n import url_sitio_oficial
        from src.services import portal_plan

        enlace_erp = (f"{url_sitio_oficial()}/registro?plan=basic&origen=b2b_onboarding_email"
                     f"&email={quote(email_login)}")
        precio_portal = portal_plan.precio_mensual_portal()
        remitente = os.environ.get("SMTP_FROM", "smart.manager.enterprises@gmail.com")
        saludo = f"Hola, equipo de {nombre_empresa}" if nombre_empresa else "Hola"
        msg = MIMEText(
            f"{saludo}:\n\n"
            f"Vimos que ya estáis comprando a vuestros proveedores a través del Portal B2B de "
            f"Smart Manager — ¡genial! Y sin comisiones, como siempre.\n\n"
            f"Si queréis dejar atrás los límites del plan Freemium (pedidos/mes, proveedores "
            f"vinculados...), tenéis dos caminos:\n\n"
            f"- Plan de Pago del Portal, desde {precio_portal}€/mes: sin límites de uso en el "
            f"Portal B2B.\n"
            f"- Smart Manager ERP (cualquier plan, desde 29€/mes): acceso completo al portal SIN "
            f"coste adicional, además de TPV, control de stock multi-almacén, compras/ventas, "
            f"facturación y mucho más, todo en un solo sitio.\n\n"
            f"Podéis ver los planes y contratar aquí: {enlace_erp}\n\n"
            f"Un saludo,\nEl equipo de Smart Manager", "plain", "utf-8")
        msg["Subject"] = "Deja atrás los límites de tu plan Freemium en el Portal B2B"
        msg["From"] = remitente
        msg["To"] = email_login

        puerto = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, puerto, timeout=10) as s:
            s.starttls()
            usuario_smtp = os.environ.get("SMTP_USER")
            password_smtp = os.environ.get("SMTP_PASSWORD")
            if usuario_smtp and password_smtp:
                s.login(usuario_smtp, password_smtp)
            s.send_message(msg)
        return True
    except Exception as e:
        logger.error("_enviar_email(%s): %s", email_login, e)
        return False


def _marcar_enviado(id_credencial):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE b2b_empresas_credenciales SET onboarding_email_enviado_en=NOW() "
                       "WHERE id=%s", (id_credencial,))
            conn.commit()
    except Exception as e:
        logger.error("_marcar_enviado(%s): %s", id_credencial, e)


def procesar() -> dict:
    """Barrido completo: envía (o descarta por ya-no-Freemium) cada candidato pendiente. Nunca lanza."""
    from src.services import portal_plan

    filas = candidatos()
    enviados = omitidos = fallidos = 0
    for f in filas:
        if portal_plan.tier_efectivo("empresa", f["id_empresa"]) != "freemium":
            # Ya tiene ERP o Plan de Pago del Portal (p. ej. contrató mientras tanto) — no se le
            # ofrece lo que ya tiene, pero SÍ se marca como gestionada para no reevaluarla cada día.
            _marcar_enviado(f["id"])
            omitidos += 1
            continue
        if _enviar_email(f["email_login"], f.get("nombre_empresa")):
            _marcar_enviado(f["id"])
            enviados += 1
        else:
            fallidos += 1
    if filas:
        logger.info("Onboarding B2B: %s candidatos, %s enviados, %s omitidos (ya exentos), "
                   "%s fallidos.", len(filas), enviados, omitidos, fallidos)
    return {"candidatos": len(filas), "enviados": enviados, "omitidos": omitidos, "fallidos": fallidos}
