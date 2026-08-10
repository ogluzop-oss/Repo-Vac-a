"""
Comercio Digital · Canal Web (módulo de creación / publicación / administración de la tienda online).

Representa el CANAL WEB como una entidad de negocio completa: ¿existe?, estado, dominio, configuración
de negocio, publicación, regeneración, sincronización y métricas. NO crea motores paralelos (N7): compone
la infraestructura existente:

  · `comercio_digital.conexiones` — endpoint + credenciales CIFRADAS (Secret Manager). La generación del
    canal crea/actualiza la conexión "web" automáticamente; el usuario NO introduce endpoint/token/auth.
  · `secret_manager` — el token de acceso se genera y se cifra (nunca en claro).
  · `publicaciones` / `catalogo` / `sync` — catálogo publicado y sincronización.
  · `pickup` / `transacciones` / `pedidos_online` — métricas operativas (pedidos, reservas Click&Collect).
  · Event Bus (CanalWeb*), RBAC (`canal_web.*`), auditoría, gobernanza.

Generación DEGRADABLE / provider-agnostic: mientras no haya hosting real (Fable 5), el canal se genera y
administra de forma abstracta (estado + conexión + tokens); al conectar un proveedor real, la misma
arquitectura publica el sitio sin rediseño. Multiempresa estricto. Aditivo/reversible.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime

from src.db.conexion import obtener_conexion

logger = logging.getLogger("cd.canal_web")

FASE = "canal_web"
ESTADOS = ("no_configurado", "generando", "publicado", "despublicado", "error")
CANAL = "web"


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)


def _puede(usuario, permiso, emp):
    perfil = (usuario or {}).get("perfil")
    if perfil in ("ADMINISTRADOR", "SUPERADMIN", "API"):
        return True
    try:
        from src.services import autorizacion
        return autorizacion.puede(usuario, permiso, id_empresa=emp)
    except Exception:
        return True


def _evento(tipo, emp, payload=None):
    try:
        from src.platform import capabilities as cap
        eb = cap.eventbus()
        if eb is not None:
            eb.publish(tipo, id_empresa=emp, ref_entidad="canal_web", ref_id=emp, payload=payload or {})
    except Exception as e:
        logger.debug("evento %s: %s", tipo, e)


def _audit(accion, emp, detalle=""):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("comercio_digital", f"CANAL_WEB_{accion}", "cd_canal_web",
                      f"empresa={emp} {detalle}"[:255])
    except Exception:
        pass


def _scalar(sql, params=()):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception:
        return 0


# ── lectura de estado ─────────────────────────────────────────────────────────
def _fila(emp) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, estado, dominio, endpoint, config_negocio, generado_en, "
                        "publicado_en, ultima_sync FROM cd_canal_web WHERE id_empresa=%s", (emp,))
            r = cur.fetchone()
            if not r:
                return None
            cols = ("id_empresa", "estado", "dominio", "endpoint", "config_negocio", "generado_en",
                    "publicado_en", "ultima_sync")
            d = r if isinstance(r, dict) else dict(zip(cols, r))
            if isinstance(d.get("config_negocio"), str):
                try:
                    d["config_negocio"] = json.loads(d["config_negocio"])
                except Exception:
                    d["config_negocio"] = {}
            return d
    except Exception as e:
        logger.error("_fila(%s): %s", emp, e)
        return None


def existe(id_empresa=None) -> bool:
    """True si la empresa tiene un canal web creado (en cualquier estado distinto de no_configurado)."""
    d = _fila(_emp(id_empresa))
    return bool(d) and d.get("estado") in ("generando", "publicado", "despublicado", "error")


def estado(id_empresa=None) -> dict:
    """Estado completo del canal (para el panel de estado). Siempre devuelve un dict (degradable)."""
    emp = _emp(id_empresa)
    d = _fila(emp)
    if not d:
        return {"id_empresa": emp, "estado": "no_configurado", "existe": False, "dominio": None,
                "config_negocio": {}}
    d["existe"] = existe(emp)
    return d


# ── generación / publicación ──────────────────────────────────────────────────
def _generar_token() -> str:
    return secrets.token_urlsafe(32)


def _guardar_conexion(emp, endpoint, token):
    """Crea/actualiza la conexión 'web' con endpoint + token CIFRADO (Secret Manager). Provider-agnostic."""
    try:
        from src.services.comercio_digital import conexiones
        conexiones.registrar(CANAL, nombre="default", id_empresa=emp, tipo_auth="apikey",
                             endpoint_base=endpoint, credenciales={"api_key": token},
                             config={"generado": True}, actor="canal_web")
        return True
    except Exception as e:
        logger.error("guardar conexion canal web: %s", e)
        return False


def _upsert(emp, **campos):
    campos.setdefault("ts_actualizado", datetime.now())
    cols = list(campos.keys())
    vals = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in campos.values()]
    set_ins = ", ".join(cols)
    ph = ", ".join(["%s"] * len(cols))
    upd = ", ".join(f"{c}=VALUES({c})" for c in cols)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO cd_canal_web (id_empresa, {set_ins}) VALUES (%s, {ph}) "
                        f"ON DUPLICATE KEY UPDATE {upd}", (emp, *vals))
            conn.commit()
        return True
    except Exception as e:
        logger.error("_upsert canal web (%s): %s", emp, e)
        return False


def crear(config_negocio=None, *, publicacion=None, id_empresa=None, usuario=None, actor=None) -> dict:
    """Crea (genera) el Canal Web a partir de la CONFIGURACIÓN DE NEGOCIO. Smart Manager genera el
    endpoint + token + auth AUTOMÁTICAMENTE (el usuario no los introduce). Estado: generando → publicado.

    `publicacion` define la MODALIDAD de dominio (reutiliza `gestion_dominios`):
      · {"tipo":"propio", "dominio":"empresa.com"}         → usa un dominio del usuario (no lo registra).
      · {"tipo":"subdominio", "nombre":"empresa"}          → genera empresa.smartmanager.ai (único).
      · {"tipo":"comprado", "dominio":"empresa.com", ...}  → lo compra vía Adapter y lo asigna.
    Sin `publicacion` se resuelve desde `config_negocio.dominio` (propio) o se genera un subdominio.
    `config_negocio` se guarda íntegra (incluidos campos futuros). RBAC `canal_web.crear`."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "canal_web.crear", emp):
        return {"ok": False, "error": "forbidden", "permiso": "canal_web.crear"}
    cfg = dict(config_negocio or {})
    from src.services.comercio_digital.canal_web import gestion_dominios as DOM
    pub = dict(publicacion or {})
    tipo_dom = pub.get("tipo") or ("propio" if (pub.get("dominio") or cfg.get("dominio")) else "subdominio")
    comprado = None
    if tipo_dom == "subdominio":
        dominio = DOM.generar_subdominio(pub.get("nombre") or cfg.get("nombre") or emp, id_empresa=emp)
    elif tipo_dom == "comprado":
        comprado = DOM.comprar_dominio(pub.get("dominio"), titular=pub.get("titular"), id_empresa=emp,
                                       usuario=usuario, proveedor=pub.get("proveedor"))
        if not comprado.get("ok"):
            return {"ok": False, "motivo": comprado.get("motivo") or "compra de dominio fallida"}
        dominio = comprado.get("dominio")
    else:  # propio
        dominio = DOM._limpio(pub.get("dominio") or cfg.get("dominio") or "")
        if not dominio or not DOM.validar_dominio(dominio):
            return {"ok": False, "motivo": "dominio propio inválido"}
    endpoint = dominio if dominio.startswith(("http://", "https://")) else f"https://{dominio}"
    cfg["dominio"] = dominio
    _upsert(emp, estado="generando", dominio=dominio, endpoint=endpoint,
            config_negocio=cfg, generado_en=datetime.now(), actor=actor or "canal_web")
    _evento("CanalWebCreating", emp, {"dominio": dominio, "tipo": tipo_dom})
    # Generación automática de credenciales (Fable 5, provider-agnostic, cifradas). Degradable.
    token = _generar_token()
    _guardar_conexion(emp, endpoint, token)
    # Registra/activa el dominio (el comprado ya se registró en comprar_dominio → asignar_dominio).
    if tipo_dom != "comprado":
        DOM.asignar_dominio(dominio, tipo=tipo_dom, id_empresa=emp)
    ok = _upsert(emp, estado="publicado", publicado_en=datetime.now())
    _evento("CanalWebCreated", emp, {"dominio": dominio})
    _evento("CanalWebPublished", emp, {"dominio": dominio})
    _audit("CREAR", emp, f"dominio={dominio} tipo={tipo_dom}")
    # Integración de duplicidades (Fase 4): `web_config` es la fuente ÚNICA de marca/activación del
    # storefront; se siembra desde la configuración de negocio del canal para que NO diverjan.
    _sync_web_config(emp, nombre=cfg.get("nombre"), dominio=dominio, activa=1)
    return {"ok": bool(ok), "estado": "publicado", "dominio": dominio, "endpoint": endpoint,
            "tipo": tipo_dom, "compra": comprado}


def _sync_web_config(emp, **campos) -> None:
    """Integración de duplicidades (Fase 4): sincroniza el subconjunto de MARCA/ACTIVACIÓN del canal
    hacia `web_config` (la fuente ÚNICA que sirve el storefront, definida en Fase 2), reutilizando la
    capa de datos `web_tienda` (N7, sin motor ni tabla nuevos). Best-effort: nunca bloquea la operación
    del canal. Evita que `config_negocio` y `web_config` muestren nombre/dominio/estado distintos."""
    try:
        from src.db import web_tienda
        campos = {k: v for k, v in campos.items() if v is not None}
        if campos:
            web_tienda.guardar_config(id_empresa=emp, **campos)
    except Exception as e:
        logger.debug("_sync_web_config: %s", e)


def actualizar_config(config_negocio, *, id_empresa=None, usuario=None) -> dict:
    """Actualiza la configuración de negocio del canal existente (sin regenerar credenciales)."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "canal_web.administrar", emp):
        return {"ok": False, "error": "forbidden", "permiso": "canal_web.administrar"}
    actual = (_fila(emp) or {}).get("config_negocio") or {}
    actual.update(dict(config_negocio or {}))
    ok = _upsert(emp, config_negocio=actual)
    # Fase 4: mantener `web_config` (fuente única de marca) alineada con el nombre/dominio del canal.
    _sync_web_config(emp, nombre=actual.get("nombre"), dominio=actual.get("dominio"))
    _evento("CanalWebConfigUpdated", emp)
    _audit("CONFIG", emp)
    return {"ok": bool(ok), "config_negocio": actual}


def config_presencia(id_empresa=None) -> dict:
    """Configuración de MARCA / PRESENCIA de la web propia (activa, nombre, descripción, color, moneda,
    logo, dominio). Canal Web es el ÚNICO propietario/editor de esta configuración (Rearquitectura CD ·
    Fase 2). Reutiliza la capa de datos existente `web_tienda` — la MISMA fila `web_config` que sirve el
    storefront (`backend/storefront.py`) — sin crear motor ni tabla nuevos (N7)."""
    from src.db import web_tienda
    return web_tienda.obtener_config(_emp(id_empresa))


def guardar_presencia(*, id_empresa=None, usuario=None, **campos) -> dict:
    """Guarda la configuración de marca/presencia (activa/nombre/descripcion/color/moneda/logo_url).
    ÚNICO editor: Canal Web. RBAC `canal_web.administrar`. Reutiliza `web_tienda.guardar_config`. Además
    mantiene el `dominio` del storefront sincronizado con el dominio gestionado por Canal Web (si no se
    pasa explícitamente), evitando que el escaparate muestre un dominio obsoleto."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "canal_web.administrar", emp):
        return {"ok": False, "error": "forbidden", "permiso": "canal_web.administrar"}
    from src.db import web_tienda
    if "dominio" not in campos:
        try:
            from src.services.comercio_digital.canal_web import gestion_dominios as _DOM
            da = _DOM.dominio_activo(emp)
            if da:
                campos["dominio"] = da.get("dominio") if isinstance(da, dict) else da
        except Exception:
            pass
    ok = web_tienda.guardar_config(id_empresa=emp, **campos)
    _evento("CanalWebConfigUpdated", emp, {"presencia": True})
    _audit("PRESENCIA", emp)
    return {"ok": bool(ok)}


def publicar(*, id_empresa=None, usuario=None) -> dict:
    emp = _emp(id_empresa)
    if not _puede(usuario, "canal_web.administrar", emp):
        return {"ok": False, "error": "forbidden", "permiso": "canal_web.administrar"}
    ok = _upsert(emp, estado="publicado", publicado_en=datetime.now())
    # Fase 4: `web_config.activa` es la ÚNICA activación que consulta el storefront → se alinea aquí.
    _sync_web_config(emp, activa=1)
    _evento("CanalWebPublished", emp)
    _audit("PUBLICAR", emp)
    return {"ok": bool(ok), "estado": "publicado"}


def despublicar(*, id_empresa=None, usuario=None) -> dict:
    emp = _emp(id_empresa)
    if not _puede(usuario, "canal_web.administrar", emp):
        return {"ok": False, "error": "forbidden", "permiso": "canal_web.administrar"}
    ok = _upsert(emp, estado="despublicado")
    # Fase 4: despublicar debe retirar el escaparate del storefront (fuente única `web_config.activa`).
    _sync_web_config(emp, activa=0)
    _evento("CanalWebUnpublished", emp)
    _audit("DESPUBLICAR", emp)
    return {"ok": bool(ok), "estado": "despublicado"}


def regenerar(*, id_empresa=None, usuario=None) -> dict:
    """Regenera las credenciales del canal (nuevo token cifrado) sin perder la configuración de negocio."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "canal_web.administrar", emp):
        return {"ok": False, "error": "forbidden", "permiso": "canal_web.administrar"}
    d = _fila(emp)
    if not d:
        return {"ok": False, "motivo": "el canal no existe"}
    token = _generar_token()
    _guardar_conexion(emp, d.get("endpoint"), token)
    _upsert(emp, estado="publicado", generado_en=datetime.now())
    _evento("CanalWebRegenerated", emp)
    _audit("REGENERAR", emp)
    return {"ok": True, "estado": "publicado"}


def sincronizar(*, id_empresa=None, usuario=None) -> dict:
    """Sincroniza el catálogo del canal reutilizando el servicio de sincronización existente."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "canal_web.administrar", emp):
        return {"ok": False, "error": "forbidden", "permiso": "canal_web.administrar"}
    res = {"ok": True}
    try:
        from src.services.tpv import catalog_sync_service as CS
        res = CS.sincronizar_catalogo()
    except Exception as e:
        logger.debug("sincronizar canal web: %s", e)
        res = {"ok": False, "motivo": str(e)}
    _upsert(emp, ultima_sync=datetime.now())
    _evento("CanalWebSynced", emp, {"resultado": res.get("ok")})
    _audit("SINCRONIZAR", emp)
    return {"ok": True, "sincronizacion": res}


# ── métricas operativas (reutilizan servicios existentes) ─────────────────────
def metricas(id_empresa=None) -> dict:
    """Métricas del canal para el panel: productos publicados, pedidos pendientes y reservas Click &
    Collect activas. Reutiliza publicaciones / pedidos_online / transacciones."""
    emp = _emp(id_empresa)
    m = {"productos_publicados": 0, "pedidos_pendientes": 0, "reservas_activas": 0}
    try:
        from src.services.comercio_digital import publicaciones
        m["productos_publicados"] = len(publicaciones.listar(id_empresa=emp, estado="PUBLICADA") or [])
    except Exception:
        pass
    m["pedidos_pendientes"] = _scalar(
        "SELECT COUNT(*) FROM pedidos_online WHERE id_empresa=%s AND estado='PENDIENTE'", (emp,))
    m["reservas_activas"] = _scalar(
        "SELECT COUNT(*) FROM transaccion_comercial WHERE id_empresa=%s AND estado IN "
        "('CONFIRMADA','PAGADA','PREPARANDO') AND metadata LIKE %s", (emp, '%PICKUP_STORE%'))
    return m


def panel(id_empresa=None) -> dict:
    """Vista agregada para el panel de administración: estado + métricas + dominios."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital.canal_web import gestion_dominios as DOM
    return {**estado(emp),
            "metricas": {**metricas(emp), **DOM.metricas_dominios(emp)},
            "dominio_activo": DOM.dominio_activo(emp),
            "dominios": DOM.listar_dominios(emp)}


def _slug(texto) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", str(texto or "tienda").lower()).strip("-")
    return s or "tienda"


def descriptor() -> dict:
    return {"servicio": "comercio_digital.canal_web", "fase": FASE, "estados": list(ESTADOS),
            "motor_nuevo": False, "generacion": "degradable/provider-agnostic", "secretos_en_claro": False,
            "reutiliza": ["conexiones (Secret Manager)", "publicaciones", "catalogo/sync", "pickup",
                          "transacciones", "eventbus", "rbac", "auditoria"],
            "operaciones": ["existe", "estado", "crear", "actualizar_config", "publicar", "despublicar",
                            "regenerar", "sincronizar", "metricas", "panel"]}


# Re-export de las operaciones de dominio (misma fachada canal_web; reutiliza gestion_dominios).
from src.services.comercio_digital.canal_web.gestion_dominios import (  # noqa: E402,F401
    activar_https, asignar_dominio, buscar_dominios, cambiar_dominio, comprar_dominio, configurar_dns,
    dominio_activo, generar_subdominio, listar_dominios, metricas_dominios, renovar_dominio,
    validar_dominio,
)

__all__ = ["FASE", "ESTADOS", "existe", "estado", "crear", "actualizar_config", "publicar",
           "despublicar", "regenerar", "sincronizar", "metricas", "panel", "descriptor",
           # dominios
           "buscar_dominios", "generar_subdominio", "comprar_dominio", "asignar_dominio",
           "cambiar_dominio", "renovar_dominio", "configurar_dns", "activar_https", "listar_dominios",
           "dominio_activo", "metricas_dominios", "validar_dominio"]
