"""
Webhooks salientes (FASE COM-9).

Suscripciones por empresa+evento con URL y secreto. `emitir_evento` entrega el payload a cada
suscripción con firma HMAC-SHA256 (cabecera X-SM-Signature) y registra el historial; reintentos
con backoff. El transporte HTTP es inyectable (`transport=`) para pruebas sin red.
"""

import hashlib
import hmac
import json
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("webhooks_salientes")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def registrar_webhook(evento, url, *, secreto=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO webhooks_suscripciones (id_empresa, evento, url, secreto) "
                        "VALUES (%s,%s,%s,%s)", (id_empresa, evento, url, secreto))
            sid = cur.lastrowid
            conn.commit()
        return sid
    except Exception as e:
        logger.error("registrar_webhook: %s", e)
        return None


def firmar(secreto, cuerpo_bytes) -> str:
    return hmac.new((secreto or "").encode("utf-8"), cuerpo_bytes, hashlib.sha256).hexdigest()


def _http_post(url, cuerpo_bytes, headers):
    """Transporte HTTP por defecto (requests). Devuelve código HTTP o None si falla."""
    try:
        import requests
        r = requests.post(url, data=cuerpo_bytes, headers=headers, timeout=10)
        return r.status_code
    except Exception as e:
        logger.info("http_post webhook: %s", e)
        return None


def emitir_evento(evento, payload, *, id_empresa=None, transport=None, max_intentos=3) -> dict:
    """Entrega `payload` a todas las suscripciones activas de `evento`. Devuelve {enviados, fallidos}."""
    id_empresa = _emp(id_empresa)
    transport = transport or _http_post
    cuerpo = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
    res = {"enviados": 0, "fallidos": 0}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, url, secreto FROM webhooks_suscripciones WHERE id_empresa=%s "
                        "AND evento=%s AND activo=1", (id_empresa, evento))
            subs = [(r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r)))
                    for r in cur.fetchall()]
    except Exception as e:
        logger.error("emitir_evento/subs: %s", e)
        return res
    for s in subs:
        headers = {"Content-Type": "application/json", "X-SM-Event": evento,
                   "X-SM-Signature": firmar(s.get("secreto"), cuerpo)}
        codigo, intentos = None, 0
        for i in range(1, int(max_intentos) + 1):
            intentos = i
            codigo = transport(s["url"], cuerpo, headers)
            if codigo and 200 <= int(codigo) < 300:
                break
        ok = bool(codigo and 200 <= int(codigo) < 300)
        res["enviados" if ok else "fallidos"] += 1
        _historial(id_empresa, s["id"], evento, s["url"], "ok" if ok else "error", codigo, intentos, cuerpo)
        _audit("WEBHOOK_ENVIADO", f"evento={evento} url={s['url']} http={codigo}")
    return res


def _historial(id_empresa, sid, evento, url, estado, codigo, intentos, cuerpo):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO webhooks_historial (id_empresa, id_suscripcion, evento, url, "
                        "estado, codigo_http, intentos, payload) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, sid, evento, url, estado, codigo, intentos,
                         cuerpo.decode("utf-8", "ignore")[:60000]))
            conn.commit()
    except Exception as e:
        logger.error("_historial: %s", e)


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("sistema", accion, "webhooks_historial", detalle)
    except Exception:
        pass
