"""Envío de la invitación al Portal de proveedor.

Orquesta: (1) asegura la cuenta/token del proveedor (`cuentas.invitar_proveedor`), (2) renderiza el correo
(`plantilla.render_invitacion`) con los datos de proveedor/empresa, (3) lo envía por la CCP corporativa
(`ccp.enviar_comunicacion`), que es DEGRADABLE: si no hay canal de correo configurado, prepara la
comunicación igualmente. Siempre devuelve el contenido renderizado (asunto/cuerpo/enlace) para que la GUI
pueda mostrarlo o copiarlo aunque el correo no llegue a salir.
"""

import os

from ._common import _audit, _emp, logger
from . import cuentas as _cuentas
from . import plantilla as _plantilla


def _nombre_empresa(id_empresa):
    try:
        from src.db.empresa import obtener_empresa
        e = obtener_empresa(id_empresa) or {}
        return e.get("nombre") or e.get("razon_social") or e.get("nombre_comercial") or "nuestra empresa"
    except Exception:
        return "nuestra empresa"


def _datos_proveedor(id_proveedor, id_empresa):
    try:
        from src.db.proveedores import obtener_proveedor
        p = obtener_proveedor(id_proveedor, id_empresa) or {}
        return p.get("razon_social") or f"Proveedor {id_proveedor}", (p.get("email") or None)
    except Exception:
        return f"Proveedor {id_proveedor}", None


def registrar_plantilla(id_empresa=None) -> int | None:
    """Registra (o actualiza) la plantilla de invitación en el catálogo de plantillas de la empresa
    (`ccp_plantillas`), en estado 'produccion'. Idempotente. Así el usuario puede verla/editarla en el
    gestor de plantillas y `ccp.enviar_comunicacion(plantilla=...)` la usa. Best-effort."""
    emp = _emp(id_empresa)
    try:
        from src.services.ccp import templates as _tpl
        tp = _plantilla.plantilla_catalogo()
        return _tpl.crear_plantilla(tp["codigo"], tp["asunto"], tp["cuerpo"], id_empresa=emp,
                                    categoria="general", idioma="es", formato="html", estado="produccion")
    except Exception as e:
        logger.debug("registrar_plantilla invitacion: %s", e)
        return None


def render_invitacion(id_proveedor, *, url_base=None, id_empresa=None) -> dict:
    """Solo renderiza la invitación (sin enviar): asegura el token y devuelve asunto/cuerpo/enlace."""
    emp = _emp(id_empresa)
    inv = _cuentas.invitar_proveedor(id_proveedor, id_empresa=emp) or {}
    token = inv.get("token", "")
    nombre, email = _datos_proveedor(id_proveedor, emp)
    empresa = _nombre_empresa(emp)
    url_base = url_base or os.getenv("PORTAL_PROVEEDOR_URL")
    r = _plantilla.render_invitacion(proveedor=nombre, empresa=empresa, token=token, url_base=url_base)
    r.update({"email": email, "token": token, "enlace": _plantilla.enlace_panel(token, url_base),
              "proveedor_nombre": nombre, "empresa_nombre": empresa})
    return r


def enviar_invitacion(id_proveedor, *, email=None, url_base=None, id_empresa=None, usuario=None) -> dict:
    """Envía (o prepara) el correo de invitación. Devuelve {ok, enviado, email, asunto, cuerpo, enlace,
    com_id, error?}. Degradable: si no hay destinatario o canal, devuelve el contenido sin enviar."""
    emp = _emp(id_empresa)
    r = render_invitacion(id_proveedor, url_base=url_base, id_empresa=emp)
    destino = (email or r.get("email") or "").strip()
    salida = {"ok": True, "enviado": False, "email": destino, "asunto": r["asunto"],
              "cuerpo": r["cuerpo_texto"], "enlace": r["enlace"], "token": r["token"], "com_id": None}
    if not destino:
        salida.update({"ok": False, "error": "sin_email"})
        return salida
    # Asegura la plantilla en el catálogo corporativo (idempotente) para poder usarla y editarla.
    registrar_plantilla(emp)
    variables = {"proveedor": r.get("proveedor_nombre") or "", "empresa": r.get("empresa_nombre") or "",
                 "token": r["token"], "enlace": r["enlace"]}
    try:
        from src.services import ccp
        # Prefiere la plantilla del catálogo (plantilla=CODIGO + variables); el asunto/cuerpo en código
        # quedan como fallback si la plantilla no renderizase.
        res = ccp.enviar_comunicacion(id_empresa=emp, destinatario=destino, asunto=r["asunto"],
                                      cuerpo=r["cuerpo_html"], canal="email", usuario=usuario,
                                      plantilla=_plantilla.CODIGO_PLANTILLA, variables=variables,
                                      metadatos={"tipo": "invitacion_portal_proveedor",
                                                 "id_proveedor": id_proveedor})
        salida["com_id"] = getattr(res, "com_id", None) or getattr(res, "id", None)
        salida["enviado"] = bool(getattr(res, "ok", False))
    except Exception as e:
        logger.debug("enviar_invitacion ccp: %s", e)
        salida["error"] = str(e)[:120]
    _audit("PORTAL_INVITACION_ENVIO", f"prov={id_proveedor} enviado={salida['enviado']}")
    return salida
