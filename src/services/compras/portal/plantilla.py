"""Plantilla del correo de invitación al Portal de proveedor.

Render en código (siempre disponible, sin depender del catálogo de plantillas de la BD). Devuelve asunto +
cuerpo HTML + cuerpo texto, con los datos del proveedor/empresa y el enlace de acceso. El envío real lo hace
`invitaciones.enviar_invitacion` a través de la CCP (degradable).
"""


# Código de la plantilla en el catálogo corporativo (ccp_plantillas). Los placeholders usan la sintaxis
# del render CCP: {{ proveedor }} / {{ empresa }} / {{ token }} / {{ enlace }}.
CODIGO_PLANTILLA = "invitacion_portal_proveedor"


def plantilla_catalogo() -> dict:
    """Asunto + cuerpo HTML de la plantilla de invitación CON placeholders `{{ }}`, para registrarla en
    el catálogo de plantillas de la empresa (editable por el usuario). Mantiene el mismo diseño que
    `render_invitacion`."""
    asunto = "{{ empresa }} te invita a su Portal de Proveedor"
    cuerpo = (
        "<div style=\"font-family:Segoe UI,Arial,sans-serif;color:#0D1117;max-width:560px\">"
        "<h2 style=\"color:#0A7\">Portal de Proveedor</h2>"
        "<p>Hola <b>{{ proveedor }}</b>:</p>"
        "<p><b>{{ empresa }}</b> usa Smart Manager para gestionar sus compras y te invita a su "
        "<b>Portal de Proveedor</b>, donde podrás mantener tus <b>tarifas</b> y <b>stock</b>, recibir "
        "los <b>pedidos</b> y marcar su estado, participar en <b>peticiones de precio (RFQ)</b> y "
        "comunicarte con el equipo de compras.</p>"
        "<p>Tu <b>token de acceso</b>:</p>"
        "<p style=\"background:#F2F4F7;border-radius:8px;padding:10px;font-family:monospace;"
        "word-break:break-all\">{{ token }}</p>"
        "<p><a href=\"{{ enlace }}\" style=\"background:#00A98F;color:#fff;text-decoration:none;"
        "padding:10px 18px;border-radius:8px;display:inline-block\">Entrar al portal</a></p>"
        "<p style=\"color:#667085;font-size:12px\">{{ enlace }}</p>"
        "<p style=\"color:#667085;font-size:12px\">Si no esperabas esta invitación, ignora este mensaje.</p>"
        "<p>Un saludo,<br>Equipo de compras de <b>{{ empresa }}</b></p>"
        "</div>")
    return {"codigo": CODIGO_PLANTILLA, "asunto": asunto, "cuerpo": cuerpo}


def enlace_panel(token, url_base=None) -> str:
    """URL del panel web del proveedor con su token. `url_base` = host donde se despliegue el backend
    (vacío hasta producción)."""
    ruta = f"/api/v1/portal-proveedor/panel?token={token}"
    base = (url_base or "").rstrip("/")
    return f"{base}{ruta}" if base else ruta


def render_invitacion(*, proveedor="proveedor", empresa="nuestra empresa", token="", url_base=None,
                      idioma="es") -> dict:
    """Devuelve {asunto, cuerpo_html, cuerpo_texto} para la invitación al portal."""
    enlace = enlace_panel(token, url_base)
    nota_enlace = enlace if (url_base or "").strip() else (
        enlace + "  (la dirección completa se activará el día del despliegue)")
    asunto = f"{empresa} te invita a su Portal de Proveedor"
    cuerpo_texto = (
        f"Hola {proveedor}:\n\n"
        f"{empresa} usa Smart Manager para gestionar sus compras y te invita a su Portal de Proveedor, "
        f"donde podrás:\n"
        f"  • Mantener tu lista de precios (tarifas) y tu stock disponible.\n"
        f"  • Recibir los pedidos y marcar su estado (aceptado, en reparto, no disponible).\n"
        f"  • Participar en peticiones de precio (RFQ) y enviar tus ofertas.\n"
        f"  • Comunicarte directamente con el equipo de compras.\n\n"
        f"Accede con tu token personal:\n{token}\n\n"
        f"Enlace de acceso:\n{nota_enlace}\n\n"
        f"Si no esperabas esta invitación, ignora este mensaje.\n\n"
        f"Un saludo,\nEquipo de compras de {empresa}\n")
    cuerpo_html = (
        f"<div style=\"font-family:Segoe UI,Arial,sans-serif;color:#0D1117;max-width:560px\">"
        f"<h2 style=\"color:#0A7\">Portal de Proveedor</h2>"
        f"<p>Hola <b>{proveedor}</b>:</p>"
        f"<p><b>{empresa}</b> usa Smart Manager para gestionar sus compras y te invita a su "
        f"<b>Portal de Proveedor</b>, donde podrás:</p>"
        f"<ul>"
        f"<li>Mantener tu lista de precios (<b>tarifas</b>) y tu <b>stock</b> disponible.</li>"
        f"<li>Recibir los <b>pedidos</b> y marcar su estado (aceptado, en reparto, no disponible).</li>"
        f"<li>Participar en <b>peticiones de precio (RFQ)</b> y enviar tus ofertas.</li>"
        f"<li>Comunicarte directamente con el equipo de compras.</li>"
        f"</ul>"
        f"<p>Tu <b>token de acceso</b>:</p>"
        f"<p style=\"background:#F2F4F7;border-radius:8px;padding:10px;font-family:monospace;"
        f"word-break:break-all\">{token}</p>"
        f"<p><a href=\"{enlace}\" style=\"background:#00A98F;color:#fff;text-decoration:none;"
        f"padding:10px 18px;border-radius:8px;display:inline-block\">Entrar al portal</a></p>"
        f"<p style=\"color:#667085;font-size:12px\">{nota_enlace}</p>"
        f"<p style=\"color:#667085;font-size:12px\">Si no esperabas esta invitación, ignora este mensaje.</p>"
        f"<p>Un saludo,<br>Equipo de compras de <b>{empresa}</b></p>"
        f"</div>")
    return {"asunto": asunto, "cuerpo_html": cuerpo_html, "cuerpo_texto": cuerpo_texto}
