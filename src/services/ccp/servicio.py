"""
Corporate Communication Service — PUNTO ÚNICO de comunicaciones de Smart Manager AI (Parte A).

Cualquier módulo que quiera comunicar (correo hoy; WhatsApp/SMS/push/firma/bots/IA mañana) llama a
`enviar_comunicacion(...)`. El servicio:
  1. genera el **Communication ID** (`COM-AAAA-NNNNNNNN`) y registra la comunicación;
  2. resuelve el destinatario/plantilla SOLO a través del Corporate Identity Resolver (nunca tablas);
  3. deja que la Channel Policy elija el canal;
  4. DELEGA el envío al canal (nunca envía directamente);
  5. actualiza estado + historial + auditoría + eventos + telemetría.

Multiempresa estricto. Núcleo agnóstico de framework.
"""

import logging
from datetime import datetime

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion
from src.services.ccp import canales as _canales
from src.services.ccp import identidad as _identidad
from src.services.ccp import politica_canal as _politica
from src.services.ccp import telemetria as _tel
from src.services.ccp.modelo import (
    Comunicacion, ESTADO_FALLIDO, ESTADO_PREPARADA, Resultado,
)

logger = logging.getLogger("ccp.servicio")


def _empresa(id_empresa):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _usuario(usuario):
    if usuario:
        return usuario
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        return str(u.get("nombre") or u.get("usuario") or u.get("id") or "") or None
    except Exception:
        return None


# ── Registro unificado de comunicaciones (Communication ID) ───────────────────
def _registrar(id_empresa, canal, destinatario, asunto, contexto, usuario) -> str | None:
    """Inserta la comunicación (estado 'preparada') y le asigna un COM-AAAA-NNNNNNNN. Devuelve com_id."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ccp_comunicaciones (id_empresa, canal, estado, destinatario, asunto, "
                "contexto, usuario) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, canal, ESTADO_PREPARADA, destinatario, asunto, contexto, usuario))
            rid = cur.lastrowid
            com_id = f"COM-{datetime.now().year}-{int(rid):08d}"
            cur.execute("UPDATE ccp_comunicaciones SET com_id=%s WHERE id=%s", (com_id, rid))
            conn.commit()
            return com_id
    except Exception as e:
        logger.debug("registrar comunicación: %s", e)
        return None


def _actualizar_estado(com_id, estado, detalle=None):
    if not com_id:
        return
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE ccp_comunicaciones SET estado=%s, detalle=%s, actualizado=NOW() "
                        "WHERE com_id=%s", (estado, (detalle or "")[:255], com_id))
            conn.commit()
    except Exception as e:
        logger.debug("actualizar estado %s: %s", com_id, e)


def _vincular_conversacion(com_id, id_empresa, correo, asunto, canal, dest_obj):
    """Asigna/continúa la Conversation del contacto y enlaza la comunicación (B4). Best-effort."""
    if not com_id or not correo:
        return
    try:
        from src.services.ccp import conversaciones as _conv
        cid = _conv.obtener_o_crear(
            id_empresa, correo=correo, asunto=asunto, canal=canal,
            entidad_tipo=getattr(dest_obj, "tipo", None), entidad_id=getattr(dest_obj, "id_origen", None))
        if cid:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE ccp_comunicaciones SET conversation_id=%s WHERE com_id=%s",
                            (cid, com_id))
                conn.commit()
    except Exception as e:
        logger.debug("vincular conversación %s: %s", com_id, e)


def historial_comunicaciones(id_empresa=None, *, canal=None, limite=200) -> list:
    """Historial unificado de comunicaciones de la empresa (auditoría por com_id)."""
    id_empresa = _empresa(id_empresa)
    q = "SELECT * FROM ccp_comunicaciones WHERE id_empresa=%s"
    p = [id_empresa]
    if canal:
        q += " AND canal=%s"; p.append(canal)
    q += " ORDER BY id DESC LIMIT %s"; p.append(int(limite))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("historial_comunicaciones: %s", e)
        return []


# ── Punto único de envío ──────────────────────────────────────────────────────
def enviar_comunicacion(*, id_empresa=None, destinatario=None, pistas=None, asunto="", cuerpo="",
                        plantilla=None, variables=None, adjuntos=None, canal=None, contexto=None,
                        usuario=None, idioma=None, prioridad="normal", id_correo=None,
                        metadatos=None) -> Resultado:
    """Envía (o prepara) una comunicación corporativa. `destinatario` puede ser un `Destinatario`, un
    correo (str) o None; si es None se resuelve con `pistas` (correo/nombre/nif/tipo) vía el Identity
    Resolver. `plantilla` (opcional) renderiza asunto/cuerpo. `canal` fuerza el canal; si no, decide la
    Channel Policy (hoy → email). Devuelve `Resultado` con el Communication ID."""
    id_empresa = _empresa(id_empresa)
    usuario = _usuario(usuario)
    if not id_empresa:
        return Resultado(ok=False, canal=canal or "email", estado=ESTADO_FALLIDO,
                         mensaje="Sin empresa: la resolución es multiempresa.")

    # 1) Resolver destinatario SOLO por el Corporate Identity Resolver.
    dest_obj, correo = None, None
    if destinatario is not None:
        if isinstance(destinatario, str):
            correo = destinatario.strip()
        else:
            dest_obj = destinatario
            correo = getattr(destinatario, "correo", None)
    elif pistas:
        dest_obj = _identidad.resolver_documento(id_empresa=id_empresa, contexto=contexto,
                                                 usuario=usuario, **pistas)
        correo = getattr(dest_obj, "correo", None)
    if not correo:
        return Resultado(ok=False, canal=canal or "email", estado=ESTADO_FALLIDO,
                         mensaje="No se pudo resolver el destinatario.")

    # 2) Plantilla corporativa (opcional): renderiza asunto/cuerpo.
    if plantilla:
        try:
            from src.services.ccp import templates as _tpl
            r = _tpl.render(plantilla, variables or {}, id_empresa=id_empresa, idioma=idioma or "es")
            if r:
                asunto, cuerpo = r
        except Exception as e:
            logger.debug("render plantilla %s: %s", plantilla, e)

    # 3) Construir comunicación + Communication ID.
    meta = dict(metadatos or {})
    if id_correo:
        meta["id_correo"] = id_correo   # buzón concreto elegido por el consumidor (p. ej. el diálogo)
    com = Comunicacion(id_empresa=id_empresa, canal=canal, destinatarios=[dest_obj or correo],
                       asunto=asunto, cuerpo=cuerpo, plantilla=plantilla, variables=variables or {},
                       idioma=idioma, prioridad=prioridad, adjuntos=adjuntos or [], contexto=contexto,
                       usuario=usuario, metadatos=meta)
    com.canal = _politica.seleccionar_canal(com, dest_obj)   # 4) Channel Policy
    com.com_id = _registrar(id_empresa, com.canal, correo, asunto, contexto, usuario)
    # B4: vincular a su Conversation (hilo) antes de enviar.
    _vincular_conversacion(com.com_id, id_empresa, correo, asunto, com.canal, dest_obj)

    # B10 · Gobierno de comunicaciones: evaluar políticas/consentimiento (decisión asociada al com_id).
    try:
        from src.services.ccp import gobierno_comunicaciones as _gob
        permitido, motivo = _gob.evaluar(id_empresa, correo, com.canal)
    except Exception:
        permitido, motivo = True, "ok"
    if not permitido:
        _actualizar_estado(com.com_id, ESTADO_FALLIDO, f"gobierno: {motivo}")
        _tel.metrica_envio(com.canal, "bloqueado")
        _tel.auditar("COMUNICACION_BLOQUEADA", f"{com.com_id} {com.canal} bloqueada: {motivo}")
        return Resultado(ok=False, canal=com.canal, com_id=com.com_id, estado=ESTADO_FALLIDO,
                         mensaje=f"Bloqueada por gobierno de comunicaciones: {motivo}")

    # 5) Delegar el envío al canal (nunca se envía aquí).
    with _tel.span("ccp.enviar", canal=com.canal):
        ch = _canales.canal(com.canal)
        if ch is None:
            res = Resultado(ok=False, canal=com.canal, com_id=com.com_id, estado=ESTADO_FALLIDO,
                            mensaje=f"Canal '{com.canal}' no registrado.")
        else:
            res = ch.enviar(com)
        res.com_id = com.com_id

    # 6) Estado + historial + auditoría + eventos + telemetría (best-effort).
    _actualizar_estado(com.com_id, res.estado, res.mensaje)
    if res.ok and correo:
        try:
            from src.services import destinatarios as _dest
            _dest.registrar_envio(correo, getattr(dest_obj, "nombre_mostrado", None),
                                  id_empresa=id_empresa, usuario=usuario, contexto=contexto)
        except Exception:
            pass
    _tel.metrica_envio(com.canal, res.estado)
    _tel.evento("COMUNICACION_ENVIADA" if res.ok else "COMUNICACION_FALLIDA", id_empresa=id_empresa,
                com_id=com.com_id, canal=com.canal, estado=res.estado, destinatario=correo,
                usuario=usuario)
    _tel.auditar("COMUNICACION", f"{com.com_id} {com.canal} {res.estado} → {correo}")
    return res
