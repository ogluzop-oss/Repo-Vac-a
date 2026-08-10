"""
PCD · Inventario · Availability Engine (CD-005) — Fase 3. Responde "¿QUÉ hay, DÓNDE y CUÁNDO?"
(ATP + buckets + ETA). GARANTÍAS (ratificadas):

  · 100 % LECTURA — no escribe, no crea reservas, no decide orígenes, NO conoce a Fulfillment.
  · Reutiliza ÍNTEGRAMENTE el inventario existente (articulos.Stock_*, stock_tienda).
  · Fachada compatible: `consultar_disponibilidad`/`localizar_articulo` conservan su forma y firma
    (la lógica se porta VERBATIM desde online_orders_service → delegación byte-idéntica, 0 regresión).
  · Salida DETERMINISTA y reconstruible: mismos datos de stock → misma respuesta.

ATP = on_hand − reservado − safety. Desde Fase 5, `reservado` proviene EXCLUSIVAMENTE del Reservation
Ledger (única fuente de bloqueo de inventario; lectura por bucket); safety=0 hasta futuras fases.
Multiempresa/multitienda.
"""

from __future__ import annotations

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("cd.availability")

BUCKETS = ("tienda_activa", "otras_tiendas", "central", "bajo_pedido")

# ETA en días (deterministas; parametrizables en fases futuras). Availability NO decide: solo informa.
ETA_INMEDIATO = 0
ETA_BAJO_PEDIDO_DEFECTO = 7


def _ctx(id_empresa=None, id_tienda="auto"):
    emp, tnd = EMPRESA_DEFAULT_ID, None
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        emp = empresa_actual_id(); tnd = tienda_actual_id()
    except Exception:
        pass
    return (id_empresa or emp), (tnd if id_tienda == "auto" else id_tienda)


# ── Fachada compatible (forma legacy idéntica a online_orders_service) ──────────
def consultar_disponibilidad(codigo: str, id_empresa=None, id_tienda="auto") -> dict:
    """Disponibilidad multi-origen en la forma histórica: stock en tienda activa, central, otras
    tiendas y online. LECTURA pura. Reproduce exactamente el resultado previo (compatibilidad)."""
    _emp, _tnd = _ctx(id_empresa, id_tienda)
    out = {"codigo": codigo, "nombre": "", "precio": 0.0, "tienda": 0, "central": 0,
           "otras_tiendas": [], "online": 0}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT nombre, COALESCE(precio,0), COALESCE(Stock_tienda,0), COALESCE(Stock_central,0) "
                "FROM articulos WHERE codigo=%s AND id_empresa=%s", (codigo, _emp))
            r = cur.fetchone()
            if r:
                if isinstance(r, dict):
                    vals = list(r.values())
                    out["nombre"] = vals[0] or ""; out["precio"] = float(vals[1] or 0)
                    out["tienda"] = int(vals[2] or 0); out["central"] = int(vals[3] or 0)
                else:
                    out["nombre"] = r[0] or ""; out["precio"] = float(r[1] or 0)
                    out["tienda"] = int(r[2] or 0); out["central"] = int(r[3] or 0)
            cur.execute(
                "SELECT st.id_tienda, COALESCE(t.nombre, CONCAT('TND-', st.id_tienda)), st.stock "
                "FROM stock_tienda st LEFT JOIN tiendas t ON t.id=st.id_tienda "
                "WHERE st.codigo_articulo=%s AND st.id_empresa=%s "
                + ("AND st.id_tienda<>%s " if _tnd is not None else "")
                + "AND st.stock>0 ORDER BY st.id_tienda",
                ((codigo, _emp, _tnd) if _tnd is not None else (codigo, _emp)))
            for f in cur.fetchall():
                tid = f[0] if not isinstance(f, dict) else f["id_tienda"]
                nom = f[1] if not isinstance(f, dict) else list(f.values())[1]
                stk = f[2] if not isinstance(f, dict) else list(f.values())[2]
                out["otras_tiendas"].append({"id_tienda": tid, "nombre": nom, "stock": int(stk or 0)})
    except Exception as e:
        logger.error("consultar_disponibilidad(%s): %s", codigo, e)
    return out


def localizar_articulo(codigo: str, id_empresa=None, id_tienda="auto") -> dict:
    """Añade banderas derivadas (compatibilidad). NO decide origen: `sugerencia` es un dato
    informativo histórico que se mantiene por compatibilidad de forma."""
    disp = consultar_disponibilidad(codigo, id_empresa, id_tienda)
    disp["disponible_tienda"] = disp.get("tienda", 0) > 0
    disp["disponible_central"] = disp.get("central", 0) > 0
    disp["disponible_otras"] = bool(disp.get("otras_tiendas"))
    disp["sugerencia"] = ("tienda" if disp["disponible_tienda"]
                          else "central" if disp["disponible_central"]
                          else "otra_tienda" if disp["disponible_otras"]
                          else "online")
    return disp


# ── API PCD: ATP + buckets + ETA (determinista) ────────────────────────────────
def disponibilidad(codigo: str, cantidad: int = 1, id_empresa=None, id_tienda="auto") -> dict:
    """Mapa de disponibilidad por bucket con ATP y ETA. LECTURA pura, determinista. NO propone
    origen ni reserva. `atp = on_hand − reservado − safety` (reservado/safety = 0 hasta Fase 5)."""
    base = consultar_disponibilidad(codigo, id_empresa, id_tienda)
    emp, _ = _ctx(id_empresa, id_tienda)
    safety = 0
    # ÚNICO descuento del ATP = el Reservation Ledger (Fase 5). Lectura del ledger por bucket.
    # (reservas es un data source de solo lectura aquí; no es Fulfillment → no rompe la separación.)
    try:
        from src.services.comercio_digital.inventario import reservas as _rsv
        _reservado = lambda bucket: _rsv.reservado(codigo, emp, bucket)   # noqa: E731
    except Exception:
        _reservado = lambda bucket: 0                                     # noqa: E731

    def _atp(on_hand, bucket):
        return max(0, int(on_hand) - _reservado(bucket) - safety)

    buckets = []
    buckets.append({"bucket": "tienda_activa", "ubicacion": "tienda",
                    "disponible": _atp(base["tienda"], "tienda_activa"), "eta_dias": ETA_INMEDIATO})
    for ot in base["otras_tiendas"]:
        buckets.append({"bucket": "otras_tiendas", "ubicacion": ot.get("nombre"),
                        "id_tienda": ot.get("id_tienda"),
                        "disponible": _atp(ot.get("stock", 0), "otras_tiendas"),
                        "eta_dias": ETA_INMEDIATO})
    buckets.append({"bucket": "central", "ubicacion": "central",
                    "disponible": _atp(base["central"], "central"), "eta_dias": ETA_INMEDIATO})
    # bajo_pedido: ETA determinista de suministro (proveedor). En Fase 3, dato informativo (0 stock).
    eta_bajo = _eta_bajo_pedido(codigo, id_empresa)
    if eta_bajo is not None:
        buckets.append({"bucket": "bajo_pedido", "ubicacion": "proveedor", "disponible": 0,
                        "eta_dias": eta_bajo})

    disponible_total = sum(b["disponible"] for b in buckets)
    return {"codigo": codigo, "nombre": base["nombre"], "cantidad_solicitada": int(cantidad),
            "buckets": buckets, "disponible_total": disponible_total,
            "cubre_solicitud": disponible_total >= int(cantidad),
            "reservado": _reservado(None), "safety": safety}


def _eta_bajo_pedido(codigo, id_empresa=None):
    """ETA de suministro por proveedor (días), determinista desde `articulos.siguiente_recepcion`
    si existe; si no, None (no se ofrece bajo_pedido). No decide nada: solo informa el 'cuándo'."""
    _emp, _tnd = _ctx(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT siguiente_recepcion FROM articulos WHERE codigo=%s AND id_empresa=%s",
                        (codigo, _emp))
            r = cur.fetchone()
        if r:
            val = r[0] if not isinstance(r, dict) else list(r.values())[0]
            if val:
                import datetime as _dt
                try:
                    fecha = val if isinstance(val, _dt.date) else _dt.date.fromisoformat(str(val)[:10])
                    return max(0, (fecha - _dt.date.today()).days)
                except Exception:
                    return ETA_BAJO_PEDIDO_DEFECTO
    except Exception:
        pass
    return None


def descriptor() -> dict:
    return {"servicio": "cd_availability", "rfc": "CD-005", "fase": 3, "estado": "implementado",
            "buckets": list(BUCKETS), "solo_lectura": True, "crea_reservas": False,
            "decide_origen": False, "conoce_fulfillment": False,
            "capacidades": ["consultar_disponibilidad", "localizar_articulo", "disponibilidad"]}


__all__ = ["BUCKETS", "consultar_disponibilidad", "localizar_articulo", "disponibilidad",
           "descriptor"]
