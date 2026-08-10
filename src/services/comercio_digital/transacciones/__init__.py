"""
PCD · Transacciones (CD-002) — Fase 2. Transacción Comercial UNIFICADA (N1/N8): entidad + máquina de
estados + timeline de eventos + historial de decisiones (N9 → Audit Replay). Piedra angular de la PCD.

- Es un SERVICIO de dominio: posee sus tablas (`transaccion_*`, migr 0139) → accede a su BD.
- Reutiliza MOTORES solo por la fachada de CAPACIDADES (`platform.capabilities`): Event Bus (eventos),
  Workflow (orquestación futura). NUNCA importa motores concretos.
- Multiempresa/multitienda; tenant del contexto.
- STRANGLER (Fase 2): registra la transacción y emite eventos; los EFECTOS de negocio (stock/fiscal/
  CCP) siguen en `pedidos_online` para no duplicarlos. `desde_pedido_online` hace el write-through.
"""

from __future__ import annotations

import json
import logging
import uuid

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion, transaccion
from src.platform import capabilities as cap

logger = logging.getLogger("cd.transacciones")

FASE = 2

TIPOS = ("presupuesto", "carrito", "reserva", "preventa", "pedido", "suscripcion", "alquiler",
         "servicio")
ESTADOS = ("BORRADOR", "CONFIRMADA", "PAGADA", "PREPARANDO", "ENVIADA", "ENTREGADA", "FACTURADA",
           "DEVUELTA", "ABONADA", "CANCELADA", "EXPIRADA")

# Máquina de estados canónica (CD-002). La validación es dominio (N10); la orquestación de tareas
# la asumirá Workflow/BPD por eventos en fases posteriores.
# EXPIRADA (aditivo, Click & Collect): una reserva de recogida no recogida en plazo expira desde
# PAGADA/PREPARANDO. NO se añade una máquina paralela: solo un estado y sus transiciones.
TRANSICIONES = {
    "BORRADOR": {"CONFIRMADA", "CANCELADA"},
    "CONFIRMADA": {"PAGADA", "CANCELADA"},
    "PAGADA": {"PREPARANDO", "CANCELADA", "EXPIRADA"},
    "PREPARANDO": {"ENVIADA", "ENTREGADA", "CANCELADA", "EXPIRADA"},
    "ENVIADA": {"ENTREGADA"},
    "ENTREGADA": {"FACTURADA", "DEVUELTA"},
    "FACTURADA": {"DEVUELTA"},
    "DEVUELTA": {"ABONADA"},
    "ABONADA": set(),
    "CANCELADA": set(),
    "EXPIRADA": set(),
}
_EVENTO = {"BORRADOR": "TxCreated", "CONFIRMADA": "TxConfirmed", "PAGADA": "TxPaid",
           "PREPARANDO": "TxPreparing", "ENVIADA": "TxShipped", "ENTREGADA": "TxDelivered",
           "FACTURADA": "TxInvoiced", "DEVUELTA": "TxRefunded", "ABONADA": "TxRefunded",
           "CANCELADA": "TxCancelled", "EXPIRADA": "TxExpired"}
# Mapa pedido_online.estado → transaccion.estado (write-through Strangler).
_MAP_PEDIDO = {"PENDIENTE": "CONFIRMADA", "PAGADO": "PAGADA", "PREPARANDO": "PREPARANDO",
               "ENVIADO": "ENVIADA", "ENTREGADO": "ENTREGADA", "CANCELADO": "CANCELADA"}


def _ctx():
    id_empresa, id_tienda, usuario, trabajador = EMPRESA_DEFAULT_ID, None, None, None
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        id_empresa = empresa_actual_id(); id_tienda = tienda_actual_id()
    except Exception:
        pass
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        usuario = u.get("id"); trabajador = u.get("nombre") or u.get("usuario")
    except Exception:
        pass
    return id_empresa, id_tienda, usuario, trabajador


def _publicar_evento(cur, id_tx, id_empresa, tipo_evento, desde, hasta, actor, payload=None):
    """Persiste el evento en el timeline y lo publica en el Event Bus (vía capacidades, degradable)."""
    cur.execute("INSERT INTO transaccion_eventos (id_tx, id_empresa, tipo_evento, estado_desde, "
                "estado_hasta, actor, payload) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (id_tx, id_empresa, tipo_evento, desde, hasta, actor,
                 json.dumps(payload) if payload else None))
    try:
        eb = cap.eventbus()
        if eb is not None:
            eb.publish(tipo_evento, id_empresa=id_empresa, ref_entidad="transaccion",
                       ref_id=id_tx, payload={"estado": hasta, "actor": actor, **(payload or {})})
    except Exception as e:
        logger.debug("publish %s: %s", tipo_evento, e)


# ── crear / leer / listar ──────────────────────────────────────────────────────
def crear(*, tipo="pedido", origen="web", estado="BORRADOR", id_empresa=None, id_tienda=None,
          cliente=None, lineas=None, direccion_envio="", moneda="EUR", referencia_externa=None,
          id_pedido_origen=None, idempotencia_key=None, metadata=None) -> str | None:
    """Crea una Transacción Comercial (cabecera + líneas) y emite TxCreated. Tenant del contexto."""
    ctx_emp, ctx_tnd, usuario, trabajador = _ctx()
    id_empresa = id_empresa or ctx_emp
    id_tienda = id_tienda if id_tienda is not None else ctx_tnd
    if tipo not in TIPOS:
        tipo = "pedido"
    if estado not in ESTADOS:
        estado = "BORRADOR"
    cliente = cliente or {}
    lineas = lineas or []
    subtotal = 0.0
    norm = []
    for l in lineas:
        cant = int(l.get("cantidad", 1) or 1)
        precio = float(l.get("precio_unitario", l.get("precio", 0)) or 0)
        sub = float(l.get("subtotal") if l.get("subtotal") is not None else cant * precio)
        subtotal += sub
        norm.append((l.get("codigo") or l.get("codigo_articulo"), l.get("nombre"),
                     l.get("tipo_producto") or "fisico", cant, precio, sub,
                     l.get("sourcing"), l.get("estado_linea") or "pendiente"))
    id_tx = str(uuid.uuid4())
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO transaccion_comercial (id_tx, id_empresa, id_tienda, origen, tipo, "
                "estado, cliente_id, cliente_nombre, cliente_telefono, cliente_email, direccion_envio,"
                " moneda, subtotal, total, referencia_externa, id_pedido_origen, usuario, trabajador, "
                "metadata, idempotencia_key) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_tx, id_empresa, id_tienda, origen, tipo, estado, cliente.get("id"),
                 cliente.get("nombre"), cliente.get("telefono"), cliente.get("email"),
                 direccion_envio, moneda, round(subtotal, 2), round(subtotal, 2),
                 referencia_externa, id_pedido_origen, usuario, trabajador,
                 json.dumps(metadata) if metadata else None, idempotencia_key))
            for codigo, nombre, tprod, cant, precio, sub, sourcing, est_l in norm:
                cur.execute(
                    "INSERT INTO transaccion_lineas (id_tx, id_empresa, codigo_articulo, nombre, "
                    "tipo_producto, cantidad, precio_unitario, subtotal, sourcing, estado_linea) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (id_tx, id_empresa, codigo, nombre, tprod, cant, precio, sub,
                     json.dumps(sourcing) if sourcing else None, est_l))
            _publicar_evento(cur, id_tx, id_empresa, "TxCreated", None, estado, trabajador,
                             {"tipo": tipo, "origen": origen})
        return id_tx
    except Exception as e:
        logger.error("crear transaccion: %s", e)
        return None


def obtener(id_tx, id_empresa=None) -> dict | None:
    id_empresa = id_empresa or _ctx()[0]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transaccion_comercial WHERE id_tx=%s AND id_empresa=%s",
                        (id_tx, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            cols = [d[0] for d in cur.description]
            tx = r if isinstance(r, dict) else dict(zip(cols, r))
            cur.execute("SELECT * FROM transaccion_lineas WHERE id_tx=%s ORDER BY id", (id_tx,))
            lcols = [d[0] for d in cur.description]
            tx["lineas"] = [x if isinstance(x, dict) else dict(zip(lcols, x)) for x in cur.fetchall()]
            return tx
    except Exception as e:
        logger.error("obtener(%s): %s", id_tx, e)
        return None


def listar(id_empresa=None, id_tienda="auto", estado=None, origen=None, limite=500) -> list:
    ctx_emp, ctx_tnd, _u, _t = _ctx()
    id_empresa = id_empresa or ctx_emp
    if id_tienda == "auto":
        id_tienda = ctx_tnd
    cond, params = ["id_empresa=%s"], [id_empresa]
    if id_tienda is not None:
        cond.append("id_tienda=%s"); params.append(id_tienda)
    if estado:
        cond.append("estado=%s"); params.append(estado)
    if origen:
        cond.append("origen=%s"); params.append(origen)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transaccion_comercial WHERE " + " AND ".join(cond) +
                        " ORDER BY creada DESC LIMIT %s", (*params, int(limite)))
            cols = [d[0] for d in cur.description]
            return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar transacciones: %s", e)
        return []


# ── máquina de estados ─────────────────────────────────────────────────────────
def transicionar(id_tx, nuevo_estado, *, actor=None, id_empresa=None, motivo=None) -> dict:
    """Valida y aplica una transición de estado; persiste evento + publica en Event Bus.
    NO ejecuta efectos de negocio en Fase 2 (siguen en pedidos_online — Strangler)."""
    id_empresa = id_empresa or _ctx()[0]
    if nuevo_estado not in ESTADOS:
        return {"ok": False, "error": f"estado inválido: {nuevo_estado}"}
    tx = obtener(id_tx, id_empresa)
    if not tx:
        return {"ok": False, "error": "transacción no encontrada"}
    actual = tx.get("estado")
    if nuevo_estado not in TRANSICIONES.get(actual, set()):
        return {"ok": False, "error": f"transición no permitida: {actual} → {nuevo_estado}"}
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE transaccion_comercial SET estado=%s WHERE id_tx=%s AND id_empresa=%s",
                        (nuevo_estado, id_tx, id_empresa))
            _publicar_evento(cur, id_tx, id_empresa, _EVENTO.get(nuevo_estado, "TxUpdated"),
                             actual, nuevo_estado, actor, {"motivo": motivo} if motivo else None)
        # Gobernanza transversal (Fase 9): comunicación de comercio vía CCP + métrica. No bloqueante,
        # degradable; fuera de la transacción para no afectar la persistencia (Strangler/aditivo).
        try:
            from src.services.comercio_digital import gobernanza
            gobernanza.metrica("commerce_tx_transicion", etiqueta=nuevo_estado)
            if nuevo_estado in ("CONFIRMADA", "PAGADA", "ENVIADA", "ENTREGADA", "CANCELADA"):
                gobernanza.notificar_cliente(f"Commerce{nuevo_estado.capitalize()}",
                                             id_empresa=id_empresa, com_id=id_tx, estado=nuevo_estado)
        except Exception as e:
            logger.debug("gobernanza (tx %s): %s", id_tx, e)
        return {"ok": True, "id_tx": id_tx, "desde": actual, "hasta": nuevo_estado}
    except Exception as e:
        logger.error("transicionar(%s): %s", id_tx, e)
        return {"ok": False, "error": str(e)}


# ── historial de decisiones (N9) ───────────────────────────────────────────────
def registrar_decision(id_tx, *, motor, decision=None, motivo=None, entradas=None, resultado=None,
                       confianza=None, actor=None, id_linea=None, id_empresa=None) -> bool:
    id_empresa = id_empresa or _ctx()[0]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO transaccion_decisiones (id_tx, id_linea, id_empresa, motor, "
                        "decision, motivo, entradas, resultado, confianza, actor) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_tx, id_linea, id_empresa, motor, decision, motivo,
                         json.dumps(entradas) if entradas else None,
                         json.dumps(resultado) if resultado else None, confianza, actor))
            conn.commit()
        return True
    except Exception as e:
        logger.error("registrar_decision(%s): %s", id_tx, e)
        return False


def eventos(id_tx, id_empresa=None) -> list:
    id_empresa = id_empresa or _ctx()[0]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transaccion_eventos WHERE id_tx=%s ORDER BY id", (id_tx,))
            cols = [d[0] for d in cur.description]
            return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:
        return []


def decisiones(id_tx, id_empresa=None) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transaccion_decisiones WHERE id_tx=%s ORDER BY id", (id_tx,))
            cols = [d[0] for d in cur.description]
            return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:
        return []


def reconstruir(id_tx, id_empresa=None) -> dict:
    """Reconstrucción íntegra (N9 → Audit Replay): estado + timeline + decisiones."""
    return {"transaccion": obtener(id_tx, id_empresa), "eventos": eventos(id_tx, id_empresa),
            "decisiones": decisiones(id_tx, id_empresa)}


# ── write-through desde pedidos_online (Strangler) ─────────────────────────────
def desde_pedido_online(id_pedido) -> str | None:
    """Espejo NO destructivo de un pedido_online en la Transacción Comercial (idempotente por
    id_pedido_origen). No re-ejecuta efectos: `pedidos_online` sigue siendo el sistema de registro."""
    try:
        # ¿ya espejado?
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_tx FROM transaccion_comercial WHERE id_pedido_origen=%s LIMIT 1",
                        (id_pedido,))
            ya = cur.fetchone()
            if ya:
                return ya[0] if not isinstance(ya, dict) else ya["id_tx"]
        from src.services.tpv import online_orders_service as OS
        ped = OS.obtener_pedido(id_pedido)
        if not ped:
            return None
        estado = _MAP_PEDIDO.get(ped.get("estado"), "CONFIRMADA")
        lineas = [{"codigo": it.get("codigo_articulo"), "nombre": it.get("nombre"),
                   "cantidad": it.get("cantidad"), "precio_unitario": it.get("precio_unitario"),
                   "subtotal": it.get("subtotal")} for it in (ped.get("items") or [])]
        return crear(tipo="pedido", origen=(ped.get("plataforma") or "web"), estado=estado,
                     id_empresa=ped.get("id_empresa"), id_tienda=ped.get("id_tienda"),
                     cliente={"id": ped.get("cliente_id"), "nombre": ped.get("cliente_nombre"),
                              "telefono": ped.get("cliente_telefono"),
                              "email": ped.get("cliente_email")},
                     lineas=lineas, direccion_envio=ped.get("direccion_envio") or "",
                     referencia_externa=ped.get("referencia_externa"), id_pedido_origen=id_pedido)
    except Exception as e:
        logger.warning("desde_pedido_online(%s): %s", id_pedido, e)
        return None


def desde_venta(venta_id, *, origen="tpv", id_empresa=None) -> str | None:
    """Espejo NO destructivo de una venta (ventas + venta_items) en la Transacción Comercial
    (idempotente por referencia 'venta:<id>'). NÚCLEO OMNICANAL (Fase 10): TPV/ventas proyectan aquí,
    igual que el canal online (`desde_pedido_online`). No re-ejecuta efectos: `ventas` sigue siendo el
    sistema de registro (Strangler). Reutiliza `crear` (mismo modelo único de Transacción Comercial)."""
    ref = f"venta:{venta_id}"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_tx FROM transaccion_comercial WHERE referencia_externa=%s LIMIT 1",
                        (ref,))
            ya = cur.fetchone()
            if ya:
                return ya[0] if not isinstance(ya, dict) else ya["id_tx"]
            cur.execute("SELECT id_empresa, id_tienda, total, forma_pago, cliente_id, cliente_nombre "
                        "FROM ventas WHERE id=%s", (venta_id,))
            v = cur.fetchone()
            if not v:
                return None
            v = v if isinstance(v, dict) else dict(zip(
                ("id_empresa", "id_tienda", "total", "forma_pago", "cliente_id", "cliente_nombre"), v))
            cur.execute("SELECT codigo_articulo, nombre, cantidad, precio_unitario, subtotal FROM "
                        "venta_items WHERE venta_id=%s", (venta_id,))
            cols = ("codigo_articulo", "nombre", "cantidad", "precio_unitario", "subtotal")
            items = [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]
        emp = id_empresa or v.get("id_empresa")
        lineas = [{"codigo": it.get("codigo_articulo"), "nombre": it.get("nombre"),
                   "cantidad": it.get("cantidad"), "precio_unitario": it.get("precio_unitario"),
                   "subtotal": it.get("subtotal")} for it in items]
        return crear(tipo="pedido", origen=origen, estado="PAGADA", id_empresa=emp,
                     id_tienda=v.get("id_tienda"),
                     cliente={"id": v.get("cliente_id"), "nombre": v.get("cliente_nombre")},
                     lineas=lineas, referencia_externa=ref,
                     idempotencia_key=f"venta:{emp}:{venta_id}",
                     metadata={"forma_pago": v.get("forma_pago"),
                               "total": float(v.get("total") or 0)})
    except Exception as e:
        logger.warning("desde_venta(%s): %s", venta_id, e)
        return None


def proyectar(origen, *, venta_id=None, id_pedido=None, id_empresa=None) -> str | None:
    """Punto ÚNICO omnicanal: proyecta una operación de cualquier canal a la Transacción Comercial.
    Delega en el espejo correspondiente (venta TPV/mostrador o pedido online). No crea modelos
    paralelos: todos los canales convergen en la misma Transacción Comercial (N1/N8)."""
    if id_pedido is not None:
        return desde_pedido_online(id_pedido)
    if venta_id is not None:
        return desde_venta(venta_id, origen=origen, id_empresa=id_empresa)
    return None


def descriptor() -> dict:
    return {"servicio": "cd_transacciones", "rfc": "CD-002", "fase": FASE, "estado": "implementado",
            "tipos": list(TIPOS), "estados": list(ESTADOS),
            "capacidades": ["crear", "obtener", "listar", "transicionar", "registrar_decision",
                            "reconstruir", "desde_pedido_online"],
            "reutiliza": ["capabilities.eventbus", "capabilities.workflow"],
            "strangler": "espeja pedidos_online sin re-ejecutar efectos"}


__all__ = ["FASE", "TIPOS", "ESTADOS", "TRANSICIONES", "crear", "obtener", "listar", "transicionar",
           "registrar_decision", "eventos", "decisiones", "reconstruir", "desde_pedido_online",
           "desde_venta", "proyectar", "descriptor"]
