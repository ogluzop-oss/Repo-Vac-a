"""
PCD · Motor de Recuperación de Carritos Abandonados (storefront público).

Mismo patrón exacto ya validado en producción para Smart Suppliers B2B
(`services.compras.b2b_carrito_abandono`), adaptado al comprador público: un carrito es candidato
cuando lleva más de `MINUTOS_UMBRAL_DEFECTO` sin cambiar de contenido (`cd_carrito_actividad`,
tocada por `carrito_storefront.anadir/actualizar_cantidad/vaciar`) Y tiene un email capturado (sin
email no hay a quién escribir — degradación honesta, nunca se inventa un destinatario). Reutiliza
`services.correo.servicio.enviar_documento` para el correo de recuperación (misma infraestructura
SMTP que el resto de notificaciones transaccionales de pedidos, `tpv.online_orders_service.
_notificar_cliente`) — el enlace de 1 clic solo necesita volver a fijar la cookie del carrito al
mismo `token_sesion` (ver `backend/storefront.py`), las líneas ya existen tal cual se dejaron.
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("cd.carrito_abandono")

MINUTOS_UMBRAL_DEFECTO = 30.0


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _candidatos(minutos_umbral) -> list[dict]:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT cl.token_sesion,
                       MIN(cl.id_empresa) AS id_empresa,
                       COUNT(*) AS n_lineas,
                       SUM(cl.cantidad * cl.precio_unitario) AS total,
                       COALESCE(act.actualizado_en, MAX(cl.creado_en)) AS ultima_actividad,
                       act.email AS email
                FROM cd_carrito_lineas cl
                LEFT JOIN cd_carrito_actividad act ON act.token_sesion = cl.token_sesion
                GROUP BY cl.token_sesion, act.email
                HAVING ultima_actividad < (NOW() - INTERVAL %s MINUTE)
            """, (float(minutos_umbral),))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("_candidatos: %s", e)
        return []


def detectar_y_marcar(minutos_umbral=MINUTOS_UMBRAL_DEFECTO) -> list[dict]:
    """Detecta carritos inactivos y persiste/actualiza `cd_carrito_abandono` — idempotente por
    `token_sesion` (no se vuelve a marcar/notificar el mismo carrito sin cambios). Devuelve SOLO
    los recién (re)marcados en ESTA pasada."""
    nuevos = []
    for c in _candidatos(minutos_umbral):
        token = c["token_sesion"]
        try:
            ensure_schema()
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT ultima_actividad, resuelto FROM cd_carrito_abandono "
                            "WHERE token_sesion=%s", (token,))
                existente = cur.fetchone()
                existente = _fila(cur, existente) if existente else None
                reflagar = (existente is None or bool(existente["resuelto"]) or
                           str(existente["ultima_actividad"]) != str(c["ultima_actividad"]))
                cur.execute(
                    "INSERT INTO cd_carrito_abandono (token_sesion, id_empresa, email, n_lineas, "
                    "total, ultima_actividad, marcado_en, notificado, resuelto) "
                    "VALUES (%s,%s,%s,%s,%s,%s,NOW(),0,0) "
                    "ON DUPLICATE KEY UPDATE id_empresa=VALUES(id_empresa), email=VALUES(email), "
                    "n_lineas=VALUES(n_lineas), total=VALUES(total), "
                    "ultima_actividad=VALUES(ultima_actividad), "
                    "marcado_en=IF(%s, NOW(), marcado_en), "
                    "notificado=IF(%s, 0, notificado), resuelto=0",
                    (token, c["id_empresa"], c.get("email"), c["n_lineas"], c["total"],
                     c["ultima_actividad"], reflagar, reflagar))
                conn.commit()
        except Exception as e:
            logger.error("detectar_y_marcar(%s): %s", token, e)
            continue
        if reflagar:
            nuevos.append(c)
    return nuevos


def listar_para_empresa(id_empresa) -> list[dict]:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cd_carrito_abandono WHERE id_empresa=%s AND resuelto=0 "
                        "ORDER BY marcado_en DESC", (id_empresa,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_para_empresa(%s): %s", id_empresa, e)
        return []


def obtener(token_sesion) -> dict | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cd_carrito_abandono WHERE token_sesion=%s", (token_sesion,))
            row = cur.fetchone()
            return _fila(cur, row) if row else None
    except Exception as e:
        logger.error("obtener(%s): %s", token_sesion, e)
        return None


def marcar_resuelto(token_sesion) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cd_carrito_abandono SET resuelto=1 WHERE token_sesion=%s", (token_sesion,))
            conn.commit()
        return True
    except Exception as e:
        logger.error("marcar_resuelto(%s): %s", token_sesion, e)
        return False


def _resolver_base_url(id_empresa) -> str:
    """URL base pública de la tienda: el dominio publicado de Canal Web (`web_config.dominio`,
    mismo criterio que `canal_web.publicar` para construir su `endpoint`) si existe, o el backend
    local (desarrollo/sin dominio propio todavía) en su defecto — nunca deja el enlace del correo
    relativo (inútil en un cliente de correo)."""
    try:
        from src.db import web_tienda
        dominio = (web_tienda.obtener_config(id_empresa) or {}).get("dominio") or ""
        dominio = dominio.strip()
        if dominio:
            return dominio if dominio.startswith(("http://", "https://")) else f"https://{dominio}"
    except Exception as e:
        logger.debug("_resolver_base_url(%s): %s", id_empresa, e)
    import os
    puerto = os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8090"))
    return f"http://127.0.0.1:{puerto}"


def _marcar_notificado(token_sesion) -> None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cd_carrito_abandono SET notificado=1 WHERE token_sesion=%s", (token_sesion,))
            conn.commit()
    except Exception as e:
        logger.debug("_marcar_notificado(%s): %s", token_sesion, e)


def enviar_recuperacion(token_sesion, *, base_url=None) -> dict:
    """Envía el correo de recuperación (1 sola vez por episodio de abandono, ver `notificado`) con
    un enlace de 1 clic que restaura el carrito. Degrada con elegancia: sin email capturado, sin
    buzón corporativo activo, o ya notificado, no hace nada y nunca lanza — igual criterio que
    `online_orders_service._notificar_cliente`."""
    reg = obtener(token_sesion)
    if not reg or reg.get("resuelto") or reg.get("notificado"):
        return {"ok": False, "motivo": "no_aplica"}
    email = (reg.get("email") or "").strip()
    if not email:
        return {"ok": False, "motivo": "sin_email_capturado"}
    id_empresa = reg["id_empresa"]
    try:
        from src.db import correo as correo_db
        buzones = correo_db.listar_correos(id_empresa)
        activos = [b for b in buzones if b.get("estado") == "activo"]
        if not activos:
            return {"ok": False, "motivo": "sin_buzon_activo"}
        id_correo = activos[0].get("id_correo")
    except Exception as e:
        logger.debug("enviar_recuperacion buzon(%s): %s", token_sesion, e)
        return {"ok": False, "motivo": "sin_buzon_activo"}
    try:
        from src.db.empresa import info_documento
        nombre_empresa = (info_documento(id_empresa) or {}).get("nombre") or "la tienda"
    except Exception:
        nombre_empresa = "la tienda"
    from src.utils import divisas
    base = (base_url or _resolver_base_url(id_empresa)).rstrip("/")
    enlace = f"{base}/tienda/{id_empresa}/carrito/restaurar?t={token_sesion}"
    asunto = f"Olvidaste algo en tu carrito de {nombre_empresa}"
    cuerpo = (
        f"Hola:\n\nDejaste {reg.get('n_lineas', 0)} artículo(s) en tu carrito "
        f"({divisas.formatear(float(reg.get('total') or 0))}). Recupéralo con un solo clic:\n\n"
        f"{enlace}\n\nUn saludo,\n{nombre_empresa}"
    )
    try:
        from src.services.correo.servicio import enviar_documento
        ok, msg = enviar_documento(id_correo, email, asunto, cuerpo)
    except Exception as e:
        logger.warning("enviar_recuperacion(%s): %s", token_sesion, e)
        return {"ok": False, "motivo": "error_envio"}
    if ok:
        _marcar_notificado(token_sesion)
    return {"ok": ok, "motivo": None if ok else (msg or "error_envio")}


def _job_detectar_y_notificar(id_empresa=None, *, base_url=None):
    """Callable del Scheduler (`fn(id_empresa)`): detecta abandonos de TODAS las empresas (el
    umbral es transversal) y envía la recuperación a cada uno recién marcado con email capturado."""
    nuevos = detectar_y_marcar()
    enviados = 0
    for c in nuevos:
        r = enviar_recuperacion(c["token_sesion"], base_url=base_url)
        if r.get("ok"):
            enviados += 1
    if nuevos:
        logger.info("carrito_abandono: %d carrito(s) marcado(s), %d email(s) de recuperación enviados",
                   len(nuevos), enviados)
    return f"nuevos={len(nuevos)} enviados={enviados}"


def registrar_jobs_abandono(id_empresa=None):
    """Registra el job en el Scheduler (idempotente) — mismo patrón exacto que
    `b2b_carrito_abandono.registrar_jobs_abandono`. La detección real (umbral de 30 min) se dispara
    cada pocos minutos desde el latido de `main.py`, no desde `ejecutar_pendientes()` (demasiado
    coarse para un umbral de minutos); el registro en el Scheduler queda para auditoría/panel."""
    try:
        from src.services import scheduler
        scheduler.registrar("cd_carrito_abandono", _job_detectar_y_notificar)
        scheduler.registrar_job("cd_carrito_abandono", intervalo_horas=1,
                                descripcion="Storefront: detectar y recuperar carritos abandonados "
                                           "(sin actividad desde hace más de 30 min)",
                                id_empresa=id_empresa)
    except Exception as e:
        logger.debug("registrar_jobs_abandono: %s", e)
