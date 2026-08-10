"""
PCD · Envíos / Logística comercial (Etapa B · Fase B7).

Genera y sigue los envíos de una Transacción Comercial mediante ADAPTADORES de transportista
(provider-agnostic, degradable; credenciales de `conexiones`, Fase B1). Reutiliza: Transacción
(estados PAGADA→PREPARANDO→ENVIADA→ENTREGADA) y Reservation Ledger (la reserva se CONSUME al enviar;
la salida física de stock la ejecuta la política única, no esta capa). Etiquetas por REFERENCIA
(nunca almacena ficheros). Multiempresa. No crea un motor nuevo.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.comercio_digital.envios.adaptador import (  # noqa: F401
    CarrierAdapter, RestCarrierAdapter, SimuladoCarrier,
)

logger = logging.getLogger("cd.envios")

FASE = "B7"

# Registro de adaptadores de transportista cargados (plugins).
_CARRIERS: dict = {}


def registrar_transportista(adapter: CarrierAdapter) -> str:
    if not isinstance(adapter, CarrierAdapter):
        raise TypeError("el adaptador debe implementar CarrierAdapter")
    if not getattr(adapter, "transportista", ""):
        raise ValueError("el adaptador debe declarar 'transportista'")
    _CARRIERS[adapter.transportista] = adapter
    return adapter.transportista


def desregistrar(transportista):
    return _CARRIERS.pop(transportista, None) is not None


def transportistas():
    return sorted(_CARRIERS)


def _carrier(transportista):
    """Adaptador registrado o, degradable, el simulado (para no romper el flujo sin transportista)."""
    return _CARRIERS.get(transportista) or SimuladoCarrier()


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
def _ctx(transportista, id_empresa):
    try:
        from src.services.comercio_digital import conexiones
        return conexiones.contexto(transportista, id_empresa=id_empresa)
    except Exception:
        from src.services.comercio_digital.canales.adaptador import AdapterContext
        return AdapterContext(id_empresa=id_empresa, canal=transportista)


# ── Ciclo de vida del envío ───────────────────────────────────────────────────
def crear_envio(id_tx, *, transportista="simulado", id_empresa=None, peso=None, direccion=None,
                actor=None):
    """Crea el envío en el transportista (etiqueta + tracking) y pasa la Transacción a PREPARANDO."""
    emp = _emp(id_empresa)
    from src.services.comercio_digital import transacciones
    tx = transacciones.obtener(id_tx, emp)
    if not tx:
        return {"ok": False, "motivo": "transacción no encontrada"}
    if tx.get("estado") not in ("PAGADA", "PREPARANDO"):
        return {"ok": False, "motivo": f"estado no válido para envío: {tx.get('estado')}"}
    carrier = _carrier(transportista)
    ctx = _ctx(transportista, emp)
    envio = {"referencia": id_tx, "direccion": direccion or tx.get("direccion_envio"),
             "peso": peso, "cliente": tx.get("cliente_nombre")}
    res = carrier.crear_envio(envio, contexto=ctx)
    estado = "etiquetado" if res.get("ok") else "preparando"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO cd_envios (id_empresa, id_tx, transportista, tracking, "
                        "etiqueta_ref, estado, peso, direccion, actor) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_tx, getattr(carrier, "transportista", transportista),
                         res.get("tracking"), res.get("etiqueta"), estado, peso,
                         direccion or tx.get("direccion_envio"), actor))
            conn.commit()
            id_envio = cur.lastrowid
    except Exception as e:
        logger.error("crear_envio(%s): %s", id_tx, e)
        return {"ok": False, "motivo": str(e)}
    if tx.get("estado") == "PAGADA":
        transacciones.transicionar(id_tx, "PREPARANDO", actor=actor or "envios", id_empresa=emp)
    return {"ok": bool(res.get("ok")), "id_envio": id_envio, "tracking": res.get("tracking"),
            "etiqueta": res.get("etiqueta"), "transportista": getattr(carrier, "transportista",
                                                                      transportista)}


def etiqueta(id_envio, *, id_empresa=None):
    e = _envio(id_envio, _emp(id_empresa))
    return e.get("etiqueta_ref") if e else None


def rastrear(id_envio, *, id_empresa=None):
    """Consulta el transportista y actualiza estado + eventos (tracking)."""
    emp = _emp(id_empresa)
    e = _envio(id_envio, emp)
    if not e:
        return {"ok": False, "motivo": "envío no encontrado"}
    carrier = _carrier(e.get("transportista"))
    r = carrier.rastrear(e.get("tracking"), contexto=_ctx(e.get("transportista"), emp))
    _actualizar(id_envio, estado=_map_estado(r.get("estado")), eventos=r.get("eventos"))
    return {"ok": True, "estado": r.get("estado"), "eventos": r.get("eventos", [])}


def registrar_incidencia(id_envio, descripcion, *, id_empresa=None):
    _actualizar(id_envio, estado="incidencia", incidencia=str(descripcion)[:255])
    return {"ok": True, "estado": "incidencia"}


def marcar_enviado(id_envio, *, id_empresa=None, actor=None):
    """Marca el envío en tránsito, pasa la Transacción a ENVIADA, CONSUME las reservas y ejecuta la
    salida física de stock por la POLÍTICA ÚNICA COMPARTIDA (`db.salida_stock`, la misma del TPV):
    kárdex + FEFO + reseed. No crea venta ni contabilidad. Idempotente (la reserva activa gobierna el
    consumo; el kárdex es idempotente por id_documento=id_tx)."""
    emp = _emp(id_empresa)
    e = _envio(id_envio, emp)
    if not e:
        return {"ok": False, "motivo": "envío no encontrado"}
    from src.services.comercio_digital import transacciones
    from src.services.comercio_digital.inventario import reservas
    tx = transacciones.obtener(e["id_tx"], emp) or {}
    tx_tienda = tx.get("id_tienda")
    consumidas = salidas = 0
    for r in reservas.activas(e["id_tx"], emp):
        if not reservas.consumir(r["id_reserva"], actor=actor or "envios", id_empresa=emp):
            continue
        consumidas += 1
        # Reserva CONSUMED → salida física REAL por la política única compartida (cierre del ciclo).
        try:
            from src.db import salida_stock as _SS
            id_t = tx_tienda if r.get("bucket") == "tienda_activa" else None
            _SS.salida_stock_oficial(r.get("codigo_articulo"), r.get("cantidad"),
                                     id_documento=e["id_tx"], id_empresa=emp, id_tienda=id_t,
                                     contexto="comercio_digital", tipo="SALIDA_VENTA",
                                     origen="COMERCIO", usuario=actor or "envios",
                                     observaciones=f"Envío pedido {e['id_tx']}")
            salidas += 1
        except Exception as ex:
            logger.debug("salida física envío (%s): %s", e["id_tx"], ex)
    res = transacciones.transicionar(e["id_tx"], "ENVIADA", actor=actor or "envios", id_empresa=emp)
    _actualizar(id_envio, estado="en_transito")
    return {"ok": bool(res.get("ok")), "estado": "en_transito", "reservas_consumidas": consumidas,
            "salidas_stock": salidas, "tx": res}


def marcar_entregado(id_envio, *, id_empresa=None, actor=None):
    emp = _emp(id_empresa)
    e = _envio(id_envio, emp)
    if not e:
        return {"ok": False, "motivo": "envío no encontrado"}
    from src.services.comercio_digital import transacciones
    res = transacciones.transicionar(e["id_tx"], "ENTREGADA", actor=actor or "envios", id_empresa=emp)
    _actualizar(id_envio, estado="entregado")
    return {"ok": bool(res.get("ok")), "estado": "entregado", "tx": res}


def listar(id_tx=None, *, id_empresa=None):
    emp = _emp(id_empresa)
    out = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = ("SELECT id, id_tx, transportista, tracking, etiqueta_ref, estado, incidencia FROM "
                   "cd_envios WHERE id_empresa=%s")
            params = [emp]
            if id_tx:
                sql += " AND id_tx=%s"
                params.append(id_tx)
            sql += " ORDER BY id DESC"
            cur.execute(sql, tuple(params))
            cols = ("id", "id_tx", "transportista", "tracking", "etiqueta_ref", "estado", "incidencia")
            for f in cur.fetchall():
                out.append(f if isinstance(f, dict) else dict(zip(cols, f)))
    except Exception as e:
        logger.error("listar envios: %s", e)
    return out


# ── helpers ───────────────────────────────────────────────────────────────────
_E_COLS = ("id", "id_tx", "transportista", "tracking", "etiqueta_ref", "estado", "eventos")


def _envio(id_envio, emp):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, id_tx, transportista, tracking, etiqueta_ref, estado, eventos "
                        "FROM cd_envios WHERE id=%s AND id_empresa=%s", (id_envio, emp))
            r = cur.fetchone()
            return (r if isinstance(r, dict) else dict(zip(_E_COLS, r))) if r else None
    except Exception as e:
        logger.error("_envio(%s): %s", id_envio, e)
        return None


def _actualizar(id_envio, *, estado=None, eventos=None, incidencia=None):
    sets, params = ["ts_actualizado=%s"], [datetime.now()]
    if estado:
        sets.append("estado=%s")
        params.append(estado)
    if eventos is not None:
        sets.append("eventos=%s")
        params.append(json.dumps(eventos, ensure_ascii=False, default=str))
    if incidencia is not None:
        sets.append("incidencia=%s")
        params.append(incidencia)
    params.append(id_envio)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE cd_envios SET {', '.join(sets)} WHERE id=%s", tuple(params))
            conn.commit()
    except Exception as e:
        logger.error("_actualizar envio(%s): %s", id_envio, e)


def _map_estado(estado_carrier):
    return {"en_transito": "en_transito", "entregado": "entregado", "incidencia": "incidencia",
            "etiquetado": "etiquetado"}.get(estado_carrier, "en_transito")


def descriptor() -> dict:
    return {"servicio": "cd_envios", "etapa": "B", "fase": FASE, "estado": "implementado",
            "transportistas_cargados": transportistas(),
            "reutiliza": ["transacciones", "reservas", "conexiones"],
            "etiqueta": "referencia (documental/storage)", "mueve_stock": False,
            "provider_agnostic": True, "crea_motor_nuevo": False}


__all__ = ["FASE", "CarrierAdapter", "SimuladoCarrier", "RestCarrierAdapter",
           "registrar_transportista", "desregistrar", "transportistas", "crear_envio", "etiqueta",
           "rastrear", "registrar_incidencia", "marcar_enviado", "marcar_entregado", "listar",
           "descriptor"]
