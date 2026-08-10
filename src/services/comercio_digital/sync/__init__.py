"""
PCD · Sync Engine (CD-002 · Fase 6). Motor de sincronización: push / pull / webhooks, con Outbox,
idempotencia, deduplicación y reintentos. SOLO infraestructura — sin lógica de ningún proveedor.

Reutilización estricta por CAPACIDADES (N7/Regla 6): Event Bus (eventos de sync), Scheduler (tareas
periódicas), Observabilidad (Correlation ID / Communication ID / tiempos / resultado / errores).
Nunca temporizadores ni hilos propios; nunca llamadas acopladas entre módulos.

Límites de la fase (restricciones ratificadas): NO mueve stock, NO crea reservas, NO consulta
Availability, NO llama a Fulfillment, NO usa IA. En entrada (pull/webhook) solo deduplica, traduce vía
adaptador y publica un evento; NUNCA muta el dominio (Canal → Dominio prohibido de forma directa).
"""

from __future__ import annotations

import logging
import time
import uuid

from src.services.comercio_digital.sync import estado, inbox, outbox  # noqa: F401

logger = logging.getLogger("cd.sync")

FASE = 6


# ── Observabilidad (Correlation ID) por capacidades, degradable ───────────────
def _correlation_id() -> str:
    from src.services.comercio_digital import _base
    return _base.correlation_id("cdsync")


# ── Event Bus por capacidades, degradable ─────────────────────────────────────
def _publicar(tipo, *, id_empresa=None, ref_id=None, payload=None):
    from src.services.comercio_digital import _base
    _base.publicar_evento(tipo, id_empresa=id_empresa, origen="comercio_digital.sync",
                          ref_entidad="cd_sync", ref_id=ref_id, payload=payload)


def _contexto_canal(canal, id_empresa, correlation_id):
    """Contexto del adaptador con credenciales resueltas desde la conexión (Etapa B/F1). Degradable:
    si no hay conexión registrada, devuelve un contexto vacío (comportamiento previo)."""
    try:
        from src.services.comercio_digital import conexiones
        return conexiones.contexto(canal, id_empresa=id_empresa, correlation_id=correlation_id)
    except Exception:
        from src.services.comercio_digital import canales
        return canales.AdapterContext(id_empresa=id_empresa, canal=canal,
                                      correlation_id=correlation_id)


# ── Push ──────────────────────────────────────────────────────────────────────
def encolar(canal, tipo, payload, *, id_empresa=None, idempotencia_key=None, communication_id=None):
    """Encola un mensaje saliente hacia un canal (idempotente). Publica evento de sync. NO transmite:
    el envío real lo hace `procesar_salientes` a través del adaptador."""
    cid = _correlation_id()
    oid = outbox.encolar(canal, tipo, payload, id_empresa=id_empresa,
                         idempotencia_key=idempotencia_key, correlation_id=cid,
                         communication_id=communication_id)
    if oid:
        _publicar("CommerceSyncQueued", id_empresa=id_empresa, ref_id=oid,
                  payload={"canal": canal, "tipo": tipo, "correlation_id": cid})
    return oid


def procesar_salientes(canal=None, *, id_empresa=None, limite=100) -> dict:
    """Procesa el Outbox: traduce (adaptador) y envía (adaptador). Registra tiempos/resultado/errores.
    Reintentos con backoff. Dominio → Adaptador → Canal."""
    from src.services.comercio_digital import canales
    t0 = time.time()
    enviados = errores = sin_adaptador = 0
    for row in outbox.pendientes(canal, id_empresa, limite):
        adapter = canales.obtener(row["canal"])
        if adapter is None:
            outbox.marcar_error(row["id"], "sin adaptador para el canal")
            sin_adaptador += 1
            errores += 1
            continue
        ctx = _contexto_canal(row["canal"], row["id_empresa"], row.get("correlation_id"))
        try:
            externo = adapter.traducir_saliente(row["payload"])
            resultado = adapter.enviar(externo, contexto=ctx)
            outbox.marcar_enviado(row["id"])
            enviados += 1
            _publicar("CommerceSyncPushed", id_empresa=row["id_empresa"], ref_id=row["id"],
                      payload={"canal": row["canal"], "correlation_id": ctx.correlation_id,
                               "resultado": resultado})
        except Exception as e:
            outbox.marcar_error(row["id"], str(e))
            errores += 1
            _publicar("CommerceSyncFailed", id_empresa=row["id_empresa"], ref_id=row["id"],
                      payload={"canal": row["canal"], "correlation_id": ctx.correlation_id,
                               "error": str(e)})
    return {"enviados": enviados, "errores": errores, "sin_adaptador": sin_adaptador,
            "ms": int((time.time() - t0) * 1000)}


# ── Pull / Webhook (solo dedup + traducción + evento; sin mutar dominio) ──────
def recibir_entrantes(canal, *, id_empresa=None, contexto=None) -> dict:
    """Pull de mensajes del canal vía adaptador. Deduplica (Inbox), traduce a neutro y publica evento.
    Devuelve los comandos neutros traducidos (para que el DOMINIO los consuma en fases posteriores).
    NO muta el dominio aquí."""
    from src.services.comercio_digital import canales
    adapter = canales.obtener(canal)
    if adapter is None:
        return {"recibidos": 0, "duplicados": 0, "comandos": []}
    ctx = contexto or _contexto_canal(canal, id_empresa, _correlation_id())
    recibidos = duplicados = 0
    comandos = []
    for ext in adapter.recibir(contexto=ctx):
        ext_id = str((ext or {}).get("id") or (ext or {}).get("external_id") or "")
        if ext_id and inbox.visto(canal, ext_id, id_empresa):
            duplicados += 1
            continue
        neutro = adapter.traducir_entrante(ext)
        clave = ext_id or ("evt-" + uuid.uuid4().hex[:12])
        if inbox.registrar(canal, clave, neutro.get("tipo", "evento"), neutro,
                           id_empresa=id_empresa, correlation_id=ctx.correlation_id) is None:
            duplicados += 1
            continue
        comandos.append(neutro)
        recibidos += 1
        _publicar("CommerceSyncReceived", id_empresa=id_empresa, ref_id=clave,
                  payload={"canal": canal, "tipo": neutro.get("tipo"),
                           "correlation_id": ctx.correlation_id})
    return {"recibidos": recibidos, "duplicados": duplicados, "comandos": comandos}


def procesar_webhook(canal, payload, *, id_empresa=None, external_id=None, firma=None,
                     cuerpo_raw=None, verificar=True) -> dict:
    """Procesa un webhook entrante único: verifica firma (HMAC, si procede), deduplica, traduce y
    publica evento. No muta el dominio. Firma inválida → rechazo; sin secreto → no_verificado."""
    from src.services.comercio_digital import canales
    adapter = canales.obtener(canal)
    if adapter is None:
        return {"ok": False, "motivo": "sin adaptador", "duplicado": False}
    cid = _correlation_id()
    verificado = None
    if verificar and firma:
        verificado = _verificar_firma(canal, cuerpo_raw if cuerpo_raw is not None else payload,
                                      firma, id_empresa)
        if verificado is False:
            return {"ok": False, "motivo": "firma inválida", "duplicado": False}
    ext_id = str(external_id or (payload or {}).get("id") or (payload or {}).get("external_id")
                 or ("wh-" + uuid.uuid4().hex[:12]))
    if inbox.visto(canal, ext_id, id_empresa):
        return {"ok": True, "duplicado": True, "verificado": verificado}
    neutro = adapter.traducir_entrante(payload or {})
    inbox.registrar(canal, ext_id, neutro.get("tipo", "webhook"), neutro, id_empresa=id_empresa,
                    correlation_id=cid)
    _publicar("CommerceSyncReceived", id_empresa=id_empresa, ref_id=ext_id,
              payload={"canal": canal, "tipo": neutro.get("tipo"), "correlation_id": cid,
                       "origen": "webhook", "verificado": verificado})
    return {"ok": True, "duplicado": False, "comando": neutro, "correlation_id": cid,
            "verificado": verificado}


# ── Sincronización real: incremental / completa (watermark) ───────────────────
def _hash(obj) -> str:
    import hashlib
    import json as _j
    return hashlib.sha256(_j.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _verificar_firma(canal, cuerpo, firma, id_empresa):
    """Verifica una firma HMAC-SHA256 con el secreto de la conexión (Fase B1). True/False, o None si no
    hay secreto (degradable). Delega en la utilidad compartida `_base`."""
    from src.services.comercio_digital import _base
    return _base.verificar_firma_webhook(canal, cuerpo, firma, id_empresa)


def sincronizar(canal, *, modo="incremental", id_empresa=None, contexto=None, limite=500) -> dict:
    """Sincronización PULL real por adaptador. `modo`='incremental' usa el watermark guardado (only
    since cursor); 'completa' trae todo. Deduplica (Inbox), detecta conflictos (mismo external_id con
    contenido distinto), avanza el watermark y publica evento. No muta el dominio."""
    from src.services.comercio_digital import canales
    adapter = canales.obtener(canal)
    if adapter is None:
        return {"ok": False, "motivo": "sin adaptador", "recibidos": 0}
    cid = _correlation_id()
    ctx = contexto or _contexto_canal(canal, id_empresa, cid)
    cur_ant = estado.cursor(canal, id_empresa) if modo == "incremental" else None
    try:
        ctx.extra = dict(ctx.extra or {})
        if modo == "incremental" and cur_ant:
            ctx.extra["cursor"] = cur_ant
        else:
            ctx.extra.pop("cursor", None)
    except Exception:
        pass
    items = adapter.recibir(contexto=ctx) or []
    recibidos = duplicados = conflictos = 0
    vistos, comandos, nuevo_cursor = {}, [], cur_ant
    for ext in items[:limite]:
        ext_id = str((ext or {}).get("id") or (ext or {}).get("external_id") or "")
        neutro = adapter.traducir_entrante(ext)
        h = _hash(neutro)
        if ext_id and ext_id in vistos:
            conflictos += (vistos[ext_id] != h)
            duplicados += (vistos[ext_id] == h)
            continue
        if ext_id:
            vistos[ext_id] = h
        if ext_id and inbox.visto(canal, ext_id, id_empresa):
            duplicados += 1
        else:
            clave = ext_id or ("evt-" + uuid.uuid4().hex[:12])
            if inbox.registrar(canal, clave, neutro.get("tipo", "evento"), neutro,
                               id_empresa=id_empresa, correlation_id=cid) is None:
                duplicados += 1
                continue
            recibidos += 1
            comandos.append(neutro)
        c = (ext or {}).get("cursor") or (ext or {}).get("updated_at") or ext_id
        if c:
            nuevo_cursor = str(c)
    estado.avanzar(canal, id_empresa, nuevo_cursor=nuevo_cursor, modo=modo, items=recibidos)
    _publicar("CommerceSyncPulled", id_empresa=id_empresa, ref_id=canal,
              payload={"modo": modo, "recibidos": recibidos, "duplicados": duplicados,
                       "conflictos": conflictos, "cursor": nuevo_cursor, "correlation_id": cid})
    return {"ok": True, "modo": modo, "recibidos": recibidos, "duplicados": duplicados,
            "conflictos": conflictos, "cursor": nuevo_cursor, "comandos": comandos}


def reprocesar_descartados(canal=None, *, id_empresa=None) -> int:
    """Recuperación de errores (dead-letter → reintento). Reutiliza el Outbox."""
    return outbox.reprocesar(canal, id_empresa)


def reconciliar(canal, referencias_remotas, *, id_empresa=None) -> dict:
    """Reconciliación: compara un conjunto de referencias del sistema externo con lo ya recibido
    (Inbox) y reporta faltantes/presentes. Solo lectura."""
    refs = [str(r) for r in (referencias_remotas or [])]
    faltantes = [r for r in refs if not inbox.visto(canal, r, id_empresa)]
    return {"canal": canal, "remotos": len(refs), "presentes": len(refs) - len(faltantes),
            "faltantes": faltantes}


# ── Scheduler (tareas periódicas por capacidad; nunca hilos/temporizadores propios) ──
def registrar_jobs() -> bool:
    """Registra el barrido de salientes en el Scheduler existente (capacidad, degradable/opt-in)."""
    try:
        from src.platform import capabilities as cap
        sch = cap.scheduler()
        if sch is not None and hasattr(sch, "registrar_job"):
            sch.registrar_job("cd_sync_push", lambda *_a, **_k: procesar_salientes())
            return True
    except Exception as e:
        logger.debug("registrar_jobs scheduler no disponible: %s", e)
    return False


def descriptor() -> dict:
    return {"servicio": "cd_sync", "rfc": "CD-002", "fase": FASE, "etapa_b": True,
            "estado": "implementado",
            "capacidades": ["push", "pull", "webhook", "outbox", "reintentos", "idempotencia",
                            "deduplicacion", "incremental", "completa", "watermark",
                            "webhook_firmado_hmac", "recuperacion_dead_letter", "reconciliacion",
                            "conflictos"],
            "reutiliza": ["eventbus", "scheduler", "observabilidad", "conexiones"],
            "mueve_stock": False, "crea_reservas": False, "consulta_availability": False,
            "llama_fulfillment": False, "usa_ia": False}


__all__ = ["FASE", "estado", "inbox", "outbox", "encolar", "procesar_salientes", "recibir_entrantes",
           "procesar_webhook", "sincronizar", "reprocesar_descartados", "reconciliar",
           "registrar_jobs", "descriptor"]
