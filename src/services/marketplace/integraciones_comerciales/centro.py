"""
Centro de Integraciones Comerciales · capa de AGREGACIÓN read-only (Fase WEB-16.5).

Alimenta la interfaz del Centro reutilizando TODO lo existente (servicio/estados/motor/adaptadores/
`online_orders`/auditoría) — no recalcula datos ni modifica el motor WEB-13 ni los conectores. Es
completamente ESCALABLE: la lista de plataformas es la UNIÓN del catálogo + los adaptadores registrados en
el motor, de modo que cualquier conector nuevo aparece automáticamente sin tocar la UI.
"""

import logging

logger = logging.getLogger("marketplace.integraciones_comerciales.centro")

# Icono por plataforma (emoji; sin pipeline de assets). Fallback genérico.
ICONOS = {"hostinger": "🌐", "woocommerce": "🛍", "shopify": "🛒", "prestashop": "🧩", "magento": "🧱",
          "opencart": "🛒", "amazon": "📦", "ebay": "🏷", "miravia": "🛒", "aliexpress": "🛒",
          "tiktok_shop": "🎵", "web_feed": "📰", "web_rest": "🔌"}

# Estado del motor → salud visual (⚪/🟡/🟢/🔴).
_SALUD = {"SINCRONIZADA": "OK", "VALIDADA": "OK", "CONFIGURADA": "WARN", "SINCRONIZANDO": "WARN",
          "ERROR": "ERROR", "NO_CONFIGURADA": "NONE", "DESHABILITADA": "NONE"}
SALUD_EMOJI = {"OK": "🟢", "WARN": "🟡", "ERROR": "🔴", "NONE": "⚪"}


def plataformas_soportadas() -> list:
    """UNIÓN del catálogo de plataformas + los adaptadores registrados en el motor. Escalable: un adaptador
    nuevo aparece solo. Cada elemento: clave/nombre/tipo/icono."""
    from src.services.marketplace.integraciones_comerciales import (
        listar_plataformas, motor)
    cat = {p["clave"]: p for p in (listar_plataformas() or [])}
    registrados = set(getattr(motor, "ADAPTADORES", {}))
    out = []
    for clave in sorted(set(cat) | registrados):
        m = cat.get(clave) or {"clave": clave, "nombre": clave.replace("_", " ").title(), "tipo": "—"}
        out.append({"clave": clave, "nombre": m.get("nombre"), "tipo": m.get("tipo") or "—",
                    "icono": ICONOS.get(clave, "🛒")})
    return out


def salud(estado: str) -> str:
    return _SALUD.get(estado, "NONE")


def _adaptador(clave):
    from src.services.marketplace.integraciones_comerciales import motor
    try:
        return motor.adaptador(clave)
    except Exception:
        return None


def _operativo(a, id_empresa):
    if a is None:
        return False
    try:
        return bool(a.disponible(id_empresa))
    except TypeError:
        try:
            return bool(a.disponible())
        except Exception:
            return False
    except Exception:
        return False


def _version(clave, id_empresa):
    a = _adaptador(clave)
    try:
        if hasattr(a, "obtener_version"):
            v = a.obtener_version(id_empresa=id_empresa)
            if v:
                return v
    except Exception:
        pass
    try:
        return type(a).version.connector_version
    except Exception:
        return None


def resumen(id_empresa, clave) -> dict:
    """Estado + salud + versión + última sincronización de UNA plataforma para la empresa."""
    from src.services.marketplace.integraciones_comerciales import servicio
    i = servicio.obtener(id_empresa, clave) or {}
    estado = i.get("estado", "NO_CONFIGURADA")
    a = _adaptador(clave)
    s = salud(estado)
    return {"clave": clave, "estado": estado, "salud": s, "salud_emoji": SALUD_EMOJI[s],
            "operativo": _operativo(a, id_empresa),
            "version": i.get("version") or _version(clave, id_empresa),
            "ultima_sync": i.get("ultima_sync"), "habilitada": i.get("habilitada", True)}


def estadisticas(id_empresa, clave) -> dict:
    """Estadísticas reutilizando datos existentes (pedidos reales por plataforma + actividad de la
    auditoría). No recalcula métricas nuevas."""
    ev = _conteo_eventos(clave)
    return {"pedidos": _pedidos(clave), "productos": ev["productos"], "clientes": ev["clientes"],
            "reservas": ev["reservas"], "stock": ev["stock"], "sincronizaciones": ev["sync"],
            "errores": ev["error"], "version_api": _version(clave, id_empresa),
            "ultima_ejecucion": ev["ultima"]}


def historial(clave, limite=50) -> list:
    """Historial (validaciones/sincronizaciones/errores/cambios) desde la auditoría existente."""
    return _auditoria(clave, limite)


def _pedidos(clave):
    try:
        from src.services.tpv import online_orders_service as OS
        return sum(1 for p in (OS.listar_pedidos_online() or [])
                   if str(p.get("plataforma")) == clave)
    except Exception:
        return "—"


def _conteo_eventos(clave, limite=1000) -> dict:
    prod = cli = res = stk = sync = err = 0
    ultima = None
    for f in _auditoria(clave, limite):
        acc = (f.get("accion") or "")
        det = (f.get("detalles") or "").lower()
        if ultima is None:
            ultima = f.get("fecha")
        if "IMPORT" in acc:
            prod += "producto" in det
            cli += "cliente" in det
            res += "reserva" in det
            stk += "stock" in det
        if "SYNC_FINISH" in acc:
            sync += 1
        if "ERROR" in acc:
            err += 1
    return {"productos": prod, "clientes": cli, "reservas": res, "stock": stk, "sync": sync,
            "error": err, "ultima": ultima}


def _auditoria(clave, limite=50) -> list:
    """Lectura read-only de `auditoria_logs` filtrada por plataforma (tabla_afectada). Reutiliza el sistema
    de auditoría existente (no crea uno paralelo)."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT accion, tabla_afectada, detalles, usuario, fecha FROM auditoria_logs "
                        "WHERE tabla_afectada=%s ORDER BY fecha DESC LIMIT %s", (clave, int(limite)))
            cols = [d[0] for d in cur.description]
            return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:
        return []
