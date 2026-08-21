"""
Política de cancelación de compras (marketplace/subasta B2B).

Motor de decisión `tipo_producto × estado × origen → acción` (según la política acordada):

  Tipo / Estado      en_cola                     pendiente                   en_preparacion
  ─────────────────  ──────────────────────────  ──────────────────────────  ──────────────────────────
  no_perecedero      libre (solo compra directa) gratuita                    recargo 10-20% / bloqueo si embalado
  perecedero         no cancelable si es subasta ventana corta (≤2 h)        bloqueo total (100%)
  bajo_pedido        no cancelable               solo si no arrancó fabric.  bloqueo total (comprador asume)

Además: SUBASTA GANADA = vinculante (no cancelación libre en cola); VENTANA DE GRACIA (60 min tras tramitar,
gratuita); STRIKE SYSTEM (demasiadas cancelaciones → se limita/pausa la capacidad de pujar).

La política es una función PURA (`politica`), fácil de probar. La orquestación (`evaluar`/`cancelar_pedido`)
reutiliza `db.compras` (no crea un flujo de pedido paralelo).
"""

import datetime as _dt
import logging

logger = logging.getLogger("compras.cancelaciones")

TIPOS = ("no_perecedero", "perecedero", "bajo_pedido")
ESTADOS = ("en_cola", "pendiente", "en_preparacion")
GRACE_MINUTOS = 60           # ventana de gracia tras tramitar (cancelación gratuita)
RECARGO_PCT = 15.0           # recargo por cancelar en preparación (restocking, dentro de 10-20%)
VENTANA_PERECEDERO_MIN = 120  # ventana corta para perecederos en 'pendiente'
STRIKE_UMBRAL = 3            # cancelaciones en la ventana → se bloquea pujar
STRIKE_DIAS = 30
_ORDEN = {"no_perecedero": 0, "perecedero": 1, "bajo_pedido": 2}


def _emp(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        return id_empresa


def politica(tipo_producto, estado, *, origen="compra_directa", minutos=None, embalado=False,
            fabricacion_iniciada=False) -> dict:
    """Decisión pura. Devuelve {puede_cancelar, recargo_pct, bloqueado, vinculante, tipo_producto,
    estado, origen, motivo}."""
    tp = tipo_producto if tipo_producto in TIPOS else "no_perecedero"
    est = estado if estado in ESTADOS else "pendiente"
    org = "subasta" if origen == "subasta" else "compra_directa"

    def R(puede, recargo=0.0, bloqueado=False, motivo=""):
        return {"puede_cancelar": bool(puede), "recargo_pct": float(recargo), "bloqueado": bool(bloqueado),
                "vinculante": org == "subasta", "tipo_producto": tp, "estado": est, "origen": org,
                "motivo": motivo}

    if est == "en_cola":
        if org == "subasta":
            return R(False, motivo="Subasta ganada: la venta es vinculante, no se cancela libremente.")
        if tp == "bajo_pedido":
            return R(False, motivo="Bajo pedido / personalizado: no cancelable.")
        return R(True, motivo="Cancelación libre en cola (compra directa).")

    if est == "pendiente":
        if minutos is not None and minutos <= GRACE_MINUTOS:
            return R(True, motivo=f"Dentro de la ventana de gracia ({GRACE_MINUTOS} min): gratuita.")
        if tp == "no_perecedero":
            return R(True, motivo="Cancelación gratuita.")
        if tp == "perecedero":
            ok = minutos is not None and minutos <= VENTANA_PERECEDERO_MIN
            return R(ok, motivo=("Perecedero: cancelación solo en la ventana corta (≤2 h)." if ok
                                 else "Perecedero: fuera de la ventana corta, no cancelable."))
        # bajo_pedido
        return R(not fabricacion_iniciada,
                 motivo=("Bajo pedido: cancelable (aún no arrancó la fabricación)." if not fabricacion_iniciada
                         else "Bajo pedido: la fabricación ya arrancó, no cancelable."))

    # en_preparacion
    if tp == "no_perecedero":
        if embalado:
            return R(False, bloqueado=True, motivo="Ya embalado: no cancelable.")
        return R(True, recargo=RECARGO_PCT,
                 motivo=f"En preparación: cancelación con recargo del {RECARGO_PCT:.0f}%.")
    return R(False, bloqueado=True,
             motivo="En preparación: bloqueo total, no cancelable" +
                    (" (el comprador asume el coste)." if tp == "bajo_pedido" else " (100%)."))


# ── Resolución del contexto de un pedido real ────────────────────────────────
def tipo_producto_pedido(id_pedido, id_empresa=None) -> str:
    """El tipo MÁS restrictivo entre las líneas del pedido (según articulos.perecibilidad)."""
    emp = _emp(id_empresa)
    try:
        from src.db.compras import obtener_pedido
        from src.db.conexion import obtener_conexion
        ped = obtener_pedido(id_pedido, emp) or {}
        codigos = [ln.get("codigo_articulo") or ln.get("codigo") for ln in (ped.get("lineas") or [])]
        codigos = [c for c in codigos if c]
        peor = "no_perecedero"
        if codigos:
            with obtener_conexion() as c, c.cursor() as cur:
                marcas = ",".join(["%s"] * len(codigos))
                cur.execute(f"SELECT perecibilidad FROM articulos WHERE codigo IN ({marcas})",
                            tuple(codigos))
                for r in cur.fetchall():
                    v = r[0] if not isinstance(r, dict) else list(r.values())[0]
                    if _ORDEN.get(v, 0) > _ORDEN.get(peor, 0):
                        peor = v
        return peor
    except Exception as e:
        logger.debug("tipo_producto_pedido: %s", e)
        return "no_perecedero"


def origen_pedido(id_pedido, id_empresa=None) -> str:
    """'subasta' si el pedido nació de una adjudicación de la Lonja; si no, 'compra_directa'."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT tipo FROM lonja_transacciones WHERE id_pedido=%s LIMIT 1", (id_pedido,))
            r = cur.fetchone()
        if r:
            t = r[0] if not isinstance(r, dict) else list(r.values())[0]
            return "subasta" if t == "adjudicacion" else "compra_directa"
    except Exception as e:
        logger.debug("origen_pedido: %s", e)
    return "compra_directa"


def estado_politica(id_pedido, id_empresa=None) -> str:
    """Estado para la política de cancelación. Por defecto 'pendiente'.
    (El estado 'en_preparacion' lo reportaba el portal externo del proveedor, ya retirado; en el futuro
    lo aportará el conector B2B para las líneas de origen 'b2b'.)"""
    return "pendiente"


def _minutos_desde_tramite(id_pedido, id_empresa=None):
    try:
        from src.db.compras import obtener_pedido
        ped = obtener_pedido(id_pedido, _emp(id_empresa)) or {}
        f = ped.get("fecha")
        if isinstance(f, _dt.datetime):
            return (_dt.datetime.now() - f).total_seconds() / 60
    except Exception:
        pass
    return None


def evaluar(id_pedido, id_empresa=None) -> dict:
    """Evalúa (sin cancelar) la política aplicable a un pedido tramitado."""
    emp = _emp(id_empresa)
    return politica(tipo_producto_pedido(id_pedido, emp), estado_politica(id_pedido, emp),
                    origen=origen_pedido(id_pedido, emp), minutos=_minutos_desde_tramite(id_pedido, emp))


def cancelar_pedido(id_pedido, *, id_empresa=None, usuario=None, forzar=False) -> dict:
    """Aplica la política y, si procede (o `forzar`), cancela el pedido y registra la cancelación."""
    from src.db import compras as C
    emp = _emp(id_empresa)
    pol = evaluar(id_pedido, emp)
    if not pol["puede_cancelar"] and not forzar:
        return {"ok": False, "politica": pol, "recargo_pct": pol["recargo_pct"], "error": "no_permitido"}
    ok = C.cancelar_pedido(id_pedido, emp)
    if ok:
        _registrar(id_pedido, pol, emp, usuario)
    return {"ok": bool(ok), "politica": pol, "recargo_pct": pol["recargo_pct"]}


def _registrar(id_pedido, pol, id_empresa, usuario):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO compras_cancelaciones (id_empresa, id_pedido, tipo_producto, estado, "
                        "origen, recargo_pct, motivo, usuario) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_pedido, pol["tipo_producto"], pol["estado"], pol["origen"],
                         pol["recargo_pct"], pol["motivo"][:255], usuario))
            c.commit()
    except Exception as e:
        logger.error("_registrar cancelacion: %s", e)


# ── Strike system ────────────────────────────────────────────────────────────
def strikes(id_empresa=None, dias=STRIKE_DIAS) -> int:
    """Nº de cancelaciones de la empresa en los últimos `dias` (para limitar pujas)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM compras_cancelaciones WHERE id_empresa=%s "
                        "AND creado_en >= (NOW() - INTERVAL %s DAY)", (emp, int(dias)))
            r = cur.fetchone()
        return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception as e:
        logger.debug("strikes: %s", e)
        return 0


def bloqueado_por_strikes(id_empresa=None) -> bool:
    """True si la empresa ha cancelado demasiado (≥ STRIKE_UMBRAL) → se le pausa la capacidad de pujar."""
    return strikes(id_empresa) >= STRIKE_UMBRAL
