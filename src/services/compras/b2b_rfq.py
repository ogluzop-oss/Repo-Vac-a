"""
Subastas inversas / Licitaciones privadas (RFQ) (Smart Suppliers B2B · Punto 2). Una empresa pide
precio de un artículo/categoría a SUS proveedores homologados; los proveedores pujan A CIEGAS (nunca ven
el precio de los demás); al cierre (manual o por vencimiento del temporizador) gana la mejor oferta y se
convierte en un Pedido B2B real.

Histórico: existió una subasta inversa casi idéntica (`services/compras/portal/rfq.py`, retirada junto
al portal externo antiguo en el commit `408548b`, recuperable con
`git show 408548b~1:src/services/compras/portal/rfq.py`). Su lógica de negocio (ordenar ofertas por
precio, una puja activa por proveedor vía upsert, cerrar/adjudicar) es el diseño de referencia probado
que se reconstruye aquí — pero NO se reutiliza su llamada de adjudicación (`db.compras.crear_pedido`,
el motor de pedidos ya superado) ni sus tablas (`portal_rfq`/`portal_rfq_ofertas`, ligadas al modelo de
sesión del portal antiguo, ya retirado). `rfq`/`rfq_ofertas` (migración 0260) son tablas limpias.

Reutiliza, sin modificarlos, motores ya existentes:
  - `services.compras.sectores.compatibles_de` (grafo de compatibilidad Empresa↔Proveedor, migración
    0217) para filtrar qué proveedores ven una RFQ — mismo criterio exacto que ya usa el catálogo B2B
    (`b2b_catalogo.buscar_para_empresa`). La relación es simétrica, así que comprobar
    `compatibles_de(sector_del_proveedor)` funciona igual de bien que desde el lado de la empresa.
  - `services.comercio_digital.transacciones` (motor único de Transacción Comercial) para la
    adjudicación: `adjudicar_rfq` crea el pedido real con el MISMO patrón exacto que
    `services.compras.b2b_pedidos.tramitar()` (`TX.crear(tipo="pedido", origen="b2b", ...)` seguido de
    `TX.transicionar(..., "CONFIRMADA", ...)`) — sin motor de pedidos/financiación paralelo. La orden
    adjudicada llega a CONFIRMADA exactamente igual que un pedido tramitado desde el carrito, así que la
    custodia de fondos (`b2b_escrow.iniciar_retencion`, que se invoca explícitamente al cobrar — no es
    automática en ninguna transición) engancha después por el mismo camino que cualquier otro pedido B2B,
    sin ningún caso especial para RFQ.
  - `db.compras.calcular_kpis_proveedor` (área "Evaluación" del backoffice, ya existente) para cruzar la
    puntuación del proveedor en el cuadro de mando comparativo (`ofertas_de_rfq`) — cálculo en vivo (no
    depende de que exista una evaluación histórica registrada), SIEMPRE con el `id_empresa` de la propia
    RFQ (nunca `None`): esa función cae a un contexto de tenant por hilo si no se le pasa, y en el
    backend Flask del portal ese contexto no tiene por qué coincidir con la empresa dueña de la RFQ.

Puja a ciegas (garantía de negocio, no solo de UI): `responder_rfq` NUNCA hace una lectura de las demás
ofertas ni las incluye en su respuesta — solo confirma la propia. `ofertas_de_rfq` (la única función que
expone el listado completo, ordenado por precio) se llama EXCLUSIVAMENTE desde el lado Empresa del
portal.
"""

import datetime as _dt
import logging
import uuid

from src.db.conexion import ensure_schema, obtener_conexion, transaccion

logger = logging.getLogger("compras.b2b_rfq")

ESTADOS_RFQ = ("abierta", "cerrada", "adjudicada", "cancelada")
ESTADOS_OFERTA = ("activa", "rechazada", "ganadora")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _filas(cur):
    cols = [d[0] for d in cur.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("compras.b2b_rfq", accion, "rfq", (detalle or "")[:255])
    except Exception:
        pass


def _obtener_rfq(id_rfq) -> dict | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rfq WHERE id_rfq=%s", (id_rfq,))
            row = cur.fetchone()
            return _fila(cur, row) if row else None
    except Exception as e:
        logger.error("_obtener_rfq(%s): %s", id_rfq, e)
        return None


# ── Alta (Portal Empresa) ───────────────────────────────────────────────────────
def crear_rfq(id_empresa, cantidad, unidad_medida, fecha_limite_entrega, fecha_cierre_subasta, *,
             codigo_articulo=None, categoria=None, sector_comercial_id=None, creado_por=None) -> str | None:
    """Da de alta una RFQ (licitación privada). `codigo_articulo`/`categoria`: al menos uno debería
    identificar QUÉ se pide (no se fuerza a nivel de esquema, igual que otras fichas del ecosistema B2B,
    pero se valida aquí). `sector_comercial_id`: normalmente el sector de la propia empresa
    (`empresas.sector_id`, ver `b2b_sesion_empresa`) — acota qué proveedores la ven vía
    `rfq_abiertas`/`sectores.compatibles_de`; `None` la deja visible a cualquier proveedor homologado
    (decisión explícita del creador, no una omisión)."""
    if not (codigo_articulo or categoria):
        logger.error("crear_rfq: falta codigo_articulo o categoria")
        return None
    try:
        cant = float(cantidad)
        if cant <= 0:
            raise ValueError("cantidad_invalida")
    except (TypeError, ValueError):
        logger.error("crear_rfq: cantidad inválida (%s)", cantidad)
        return None
    if not fecha_cierre_subasta:
        logger.error("crear_rfq: falta fecha_cierre_subasta")
        return None
    id_rfq = str(uuid.uuid4())
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rfq (id_rfq, id_empresa, codigo_articulo, categoria, cantidad, "
                "unidad_medida, fecha_limite_entrega, fecha_cierre_subasta, sector_comercial_id, "
                "creado_por) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_rfq, id_empresa, codigo_articulo, categoria, cant,
                 str(unidad_medida or "unidad"), fecha_limite_entrega, fecha_cierre_subasta,
                 sector_comercial_id, creado_por))
        _audit("RFQ_ALTA", f"{id_rfq}:emp={id_empresa} {codigo_articulo or categoria} x{cant}")
        return id_rfq
    except Exception as e:
        logger.error("crear_rfq(%s): %s", id_empresa, e)
        return None


def obtener_rfq(id_rfq, id_empresa) -> dict | None:
    """Lectura de una RFQ concreta ACOTADA a la empresa dueña (evita que el Portal Empresa muestre/
    adjudique una RFQ de otra empresa por IDOR aunque se adivine el UUID) — usada por las rutas de
    detalle/adjudicación; `_obtener_rfq` (sin filtro de tenant) queda para el job programado y el lado
    Proveedor, que legítimamente no parten de una sesión de empresa."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rfq WHERE id_rfq=%s AND id_empresa=%s", (id_rfq, id_empresa))
            row = cur.fetchone()
            return _fila(cur, row) if row else None
    except Exception as e:
        logger.error("obtener_rfq(%s,%s): %s", id_rfq, id_empresa, e)
        return None


def listar_rfq(id_empresa, *, estado=None, limite=200) -> list:
    """RFQs de una empresa (lado Portal Empresa: índice + selección de detalle)."""
    try:
        ensure_schema()
        cond, params = ["id_empresa=%s"], [id_empresa]
        if estado:
            cond.append("estado=%s"); params.append(estado)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM rfq WHERE {' AND '.join(cond)} "
                        f"ORDER BY fecha_creacion DESC LIMIT %s", (*params, int(limite)))
            return _filas(cur)
    except Exception as e:
        logger.error("listar_rfq(%s): %s", id_empresa, e)
        return []


# ── Lado Proveedor ───────────────────────────────────────────────────────────────
def rfq_abiertas(sector_comercial_id=None) -> list:
    """RFQs abiertas y aún no vencidas, para el Portal Proveedor. `sector_comercial_id`: el sector DEL
    PROVEEDOR que consulta — se filtra con `sectores.compatibles_de` (relación simétrica, ver docstring
    del módulo). Una RFQ sin sector fijado (`sector_comercial_id IS NULL`) es visible para cualquiera.
    NUNCA incluye ofertas — solo cabecera de la RFQ (ver `ofertas_de_rfq` para el motivo de ese límite)."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rfq WHERE estado='abierta' AND fecha_cierre_subasta > NOW() "
                        "ORDER BY fecha_cierre_subasta ASC")
            filas = _filas(cur)
    except Exception as e:
        logger.error("rfq_abiertas: %s", e)
        return []
    if not sector_comercial_id:
        return filas
    try:
        from src.services.compras import sectores
        compat = sectores.compatibles_de(sector_comercial_id)
    except Exception as e:
        logger.error("rfq_abiertas: compatibles_de(%s): %s", sector_comercial_id, e)
        return filas
    return [r for r in filas if not r.get("sector_comercial_id")
            or int(r["sector_comercial_id"]) in compat]


def responder_rfq(id_rfq, id_suministrador, precio_unitario, moq=None, plazo_entrega_dias=None) -> dict:
    """Puja A CIEGAS: upsert (INSERT...ON DUPLICATE KEY UPDATE, amparado por la `UNIQUE KEY
    uq_rfq_oferta` de la migración 0260 — una puja activa por proveedor, garantía de motor, no solo de
    aplicación) sobre la oferta de ESTE proveedor. Devuelve EXCLUSIVAMENTE la confirmación de su propia
    oferta — nunca consulta ni puede filtrar accidentalmente el precio de otro proveedor, porque no lee
    `rfq_ofertas` salvo por `(id_rfq, id_suministrador)` de quien llama."""
    rfq = _obtener_rfq(id_rfq)
    if not rfq:
        return {"ok": False, "error": "rfq_no_encontrada"}
    if rfq.get("estado") != "abierta":
        return {"ok": False, "error": "rfq_no_abierta"}
    cierre = rfq.get("fecha_cierre_subasta")
    if isinstance(cierre, str):
        cierre = _dt.datetime.fromisoformat(cierre[:19])
    if cierre and cierre <= _dt.datetime.now():
        return {"ok": False, "error": "plazo_vencido"}
    try:
        precio = float(precio_unitario)
        if precio <= 0:
            raise ValueError("precio_invalido")
    except (TypeError, ValueError):
        return {"ok": False, "error": "precio_invalido"}
    try:
        moq_v = float(moq) if moq not in (None, "") else None
    except (TypeError, ValueError):
        moq_v = None
    try:
        plazo_v = int(plazo_entrega_dias) if plazo_entrega_dias not in (None, "") else None
    except (TypeError, ValueError):
        plazo_v = None

    id_oferta_nueva = str(uuid.uuid4())
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rfq_ofertas (id_oferta, id_rfq, id_suministrador, precio_unitario, moq, "
                "plazo_entrega_dias, estado) VALUES (%s,%s,%s,%s,%s,%s,'activa') "
                "ON DUPLICATE KEY UPDATE precio_unitario=VALUES(precio_unitario), moq=VALUES(moq), "
                "plazo_entrega_dias=VALUES(plazo_entrega_dias), estado='activa'",
                (id_oferta_nueva, id_rfq, id_suministrador, precio, moq_v, plazo_v))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_oferta, precio_unitario, moq, plazo_entrega_dias, fecha_oferta, "
                        "estado FROM rfq_ofertas WHERE id_rfq=%s AND id_suministrador=%s",
                        (id_rfq, id_suministrador))
            row = cur.fetchone()
            propia = _fila(cur, row) if row else None
    except Exception as e:
        logger.error("responder_rfq(%s,%s): %s", id_rfq, id_suministrador, e)
        return {"ok": False, "error": "error_registrando_oferta"}
    if not propia:
        return {"ok": False, "error": "error_registrando_oferta"}
    _audit("RFQ_OFERTA", f"rfq={id_rfq} sum={id_suministrador} precio={precio}")
    return {"ok": True, "id_oferta": propia["id_oferta"], "precio_unitario": float(propia["precio_unitario"]),
            "moq": float(propia["moq"]) if propia.get("moq") is not None else None,
            "plazo_entrega_dias": propia.get("plazo_entrega_dias"), "fecha_oferta": propia.get("fecha_oferta")}


def mi_oferta(id_rfq, id_suministrador) -> dict | None:
    """La oferta propia de un proveedor en una RFQ (o `None` si no ha pujado todavía) — para el lado
    Proveedor del portal, que nunca debe poder ver ofertas ajenas: a diferencia de `ofertas_de_rfq`, esta
    consulta está acotada por `id_suministrador` desde el propio SQL, no filtrada en Python después de
    leer todo el listado."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_oferta, precio_unitario, moq, plazo_entrega_dias, fecha_oferta, "
                        "estado FROM rfq_ofertas WHERE id_rfq=%s AND id_suministrador=%s",
                        (id_rfq, id_suministrador))
            row = cur.fetchone()
            return _fila(cur, row) if row else None
    except Exception as e:
        logger.error("mi_oferta(%s,%s): %s", id_rfq, id_suministrador, e)
        return None


# ── Lado Empresa: cuadro de mando comparativo ───────────────────────────────────
def ofertas_de_rfq(id_rfq) -> list:
    """TODAS las ofertas de una RFQ, ordenadas por precio ascendente, con el nombre del proveedor y su
    puntuación de Evaluación (`db.compras.calcular_kpis_proveedor`, la misma que respalda el área
    "Evaluación" del backoffice) cuando el proveedor está vinculado a un `id_proveedor` tradicional de
    esta empresa (`proveedores.id_suministrador`, migración 0218) — `None` si no lo está (proveedor
    homologado vía RFQ sin alta completa en el maestro de proveedores todavía).

    ÚNICA función que expone el listado completo de ofertas — llamar solo desde el lado Empresa del
    portal (o el job de cierre automático); NUNCA desde el lado Proveedor (ver `responder_rfq`, que
    garantiza la puja a ciegas por diseño al no usar esta función)."""
    rfq = _obtener_rfq(id_rfq)
    if not rfq:
        return []
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT o.*, COALESCE(s.razon_social, CONCAT('Proveedor ', o.id_suministrador)) "
                "AS proveedor, p.id_proveedor AS id_proveedor "
                "FROM rfq_ofertas o "
                "LEFT JOIN suministradores s ON s.id = o.id_suministrador "
                "LEFT JOIN proveedores p ON p.id_suministrador = o.id_suministrador "
                "AND p.id_empresa = %s "
                "WHERE o.id_rfq=%s ORDER BY o.precio_unitario ASC", (rfq["id_empresa"], id_rfq))
            filas = _filas(cur)
    except Exception as e:
        logger.error("ofertas_de_rfq(%s): %s", id_rfq, e)
        return []
    from src.db import compras as C
    for f in filas:
        f["valoracion_global"] = None
        if f.get("id_proveedor"):
            try:
                kpis = C.calcular_kpis_proveedor(f["id_proveedor"], id_empresa=rfq["id_empresa"])
                f["valoracion_global"] = kpis.get("valoracion_global")
            except Exception as e:
                logger.debug("ofertas_de_rfq: kpis proveedor %s: %s", f["id_proveedor"], e)
    return filas


# ── Adjudicación ─────────────────────────────────────────────────────────────────
def adjudicar_rfq(id_rfq, id_suministrador, usuario=None) -> dict:
    """Adjudica la RFQ a `id_suministrador`: reclama la RFQ (UPDATE condicional `estado='abierta' →
    'adjudicada'`, mismo patrón de "rowcount como guardia de carrera" que
    `transacciones.transicionar`/`b2b_escrow`), crea el Pedido B2B real con el MISMO patrón exacto que
    `b2b_pedidos.tramitar()` (`TX.crear(origen='b2b', tipo='pedido', ...)` →
    `TX.transicionar(..., 'CONFIRMADA', ...)`), y solo entonces marca la oferta ganadora/las demás
    rechazadas. Si el pedido no llega a CONFIRMADA (fallo del motor de transacciones), la reclamación se
    revierte (`estado` vuelve a 'abierta') — nunca deja la RFQ 'adjudicada' sin un pedido real detrás."""
    rfq = _obtener_rfq(id_rfq)
    if not rfq:
        return {"ok": False, "error": "rfq_no_encontrada"}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rfq_ofertas WHERE id_rfq=%s AND id_suministrador=%s",
                        (id_rfq, id_suministrador))
            row = cur.fetchone()
            oferta = _fila(cur, row) if row else None
    except Exception as e:
        logger.error("adjudicar_rfq: leyendo oferta (%s,%s): %s", id_rfq, id_suministrador, e)
        return {"ok": False, "error": "error_leyendo_oferta"}
    if not oferta or oferta.get("estado") != "activa":
        return {"ok": False, "error": "oferta_no_encontrada_o_no_activa"}

    try:
        with transaccion() as conn, conn.cursor() as cur:
            afectadas = cur.execute(
                "UPDATE rfq SET estado='adjudicada' WHERE id_rfq=%s AND estado='abierta'", (id_rfq,))
    except Exception as e:
        logger.error("adjudicar_rfq: reclamando rfq %s: %s", id_rfq, e)
        return {"ok": False, "error": "error_reclamando_rfq"}
    if not afectadas:
        return {"ok": False, "error": "rfq_no_abierta_o_ya_adjudicada"}

    id_tx = None
    try:
        from src.services.comercio_digital import transacciones as TX
        codigo = rfq.get("codigo_articulo") or f"RFQ-{id_rfq[:8]}"
        lineas = [{"codigo": codigo, "nombre": rfq.get("categoria") or codigo,
                  "cantidad": float(rfq["cantidad"]), "precio_unitario": float(oferta["precio_unitario"])}]
        id_tx = TX.crear(tipo="pedido", origen="b2b", estado="BORRADOR", id_empresa=rfq["id_empresa"],
                         lineas=lineas, metadata={"id_rfq": id_rfq, "id_suministrador": id_suministrador,
                                                  "usuario": usuario, "via": "rfq_adjudicacion"})
        if not id_tx:
            raise RuntimeError("transacciones.crear devolvió None")
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE transaccion_comercial SET id_suministrador=%s WHERE id_tx=%s",
                       (id_suministrador, id_tx))
            if rfq.get("codigo_articulo"):
                cur.execute("UPDATE transaccion_lineas SET unidad_medida=%s WHERE id_tx=%s "
                           "AND codigo_articulo=%s", (rfq.get("unidad_medida"), id_tx, codigo))
            conn.commit()
        r = TX.transicionar(id_tx, "CONFIRMADA", actor=usuario, id_empresa=rfq["id_empresa"],
                            motivo=f"RFQ {id_rfq} adjudicada a suministrador {id_suministrador}")
        if not r.get("ok"):
            raise RuntimeError(f"transicionar CONFIRMADA: {r.get('error')}")
    except Exception as e:
        logger.error("adjudicar_rfq(%s,%s): %s", id_rfq, id_suministrador, e)
        try:
            with transaccion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE rfq SET estado='abierta' WHERE id_rfq=%s AND estado='adjudicada'",
                           (id_rfq,))
        except Exception as e2:
            logger.error("adjudicar_rfq: no se pudo revertir la reclamación de %s: %s", id_rfq, e2)
        return {"ok": False, "error": "error_creando_pedido_b2b"}

    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE rfq_ofertas SET estado='ganadora' WHERE id_rfq=%s AND id_suministrador=%s",
                       (id_rfq, id_suministrador))
            cur.execute("UPDATE rfq_ofertas SET estado='rechazada' WHERE id_rfq=%s "
                       "AND id_suministrador<>%s AND estado='activa'", (id_rfq, id_suministrador))
    except Exception as e:
        # El pedido YA está creado y CONFIRMADA (lo importante, fuente de verdad) — un fallo aquí solo
        # deja las ofertas perdedoras sin marcar 'rechazada' visualmente, no rompe nada funcional.
        logger.error("adjudicar_rfq: marcando ofertas de %s: %s", id_rfq, e)

    _audit("ADJUDICAR", f"{id_rfq}:sum={id_suministrador} tx={id_tx}")
    return {"ok": True, "id_rfq": id_rfq, "id_suministrador": id_suministrador, "id_tx": id_tx,
            "precio_unitario": float(oferta["precio_unitario"]), "cantidad": float(rfq["cantidad"])}


# ── Job programado ───────────────────────────────────────────────────────────────
def cerrar_rfq_vencidas() -> list:
    """Job de scheduler: toda RFQ 'abierta' cuya `fecha_cierre_subasta` ya pasó se resuelve sola — con
    al menos una oferta viva, adjudica automáticamente a la más barata (mismo camino que una
    adjudicación manual, vía `adjudicar_rfq`); sin ninguna oferta, se marca 'cerrada' sin adjudicar
    (nada que adjudicar)."""
    resultados = []
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_rfq FROM rfq WHERE estado='abierta' AND fecha_cierre_subasta <= NOW()")
            vencidas = [r[0] if not isinstance(r, dict) else r["id_rfq"] for r in cur.fetchall()]
    except Exception as e:
        logger.error("cerrar_rfq_vencidas (consulta): %s", e)
        return []
    for id_rfq in vencidas:
        activas = [o for o in ofertas_de_rfq(id_rfq) if o.get("estado") == "activa"]
        if activas:
            mejor = activas[0]  # ofertas_de_rfq ya ordena por precio_unitario ASC
            r = adjudicar_rfq(id_rfq, mejor["id_suministrador"], usuario="scheduler")
            resultados.append({"id_rfq": id_rfq, "accion": "adjudicada" if r.get("ok") else "error",
                               "detalle": r})
        else:
            try:
                with transaccion() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE rfq SET estado='cerrada' WHERE id_rfq=%s AND estado='abierta'",
                               (id_rfq,))
                resultados.append({"id_rfq": id_rfq, "accion": "cerrada_sin_ofertas"})
            except Exception as e:
                logger.error("cerrar_rfq_vencidas: cerrando %s sin ofertas: %s", id_rfq, e)
                resultados.append({"id_rfq": id_rfq, "accion": "error", "detalle": str(e)})
    return resultados


def registrar_jobs_rfq(id_empresa=None):
    """Registra el job de cierre/adjudicación automática (mismo patrón exacto que
    `b2b_escrow.registrar_jobs_escrow`/`b2b_rappels.registrar_jobs_rappels`). Intervalo de 1 hora
    (frente a las 24h de rappels/escrow): una subasta tiene una hora de cierre concreta que el
    proveedor ve en pantalla — dejarla "abierta" medio día de más tras vencer degradaría la confianza en
    el mecanismo (a diferencia de un rappel de ventana anual o una liberación de fondos con 3 días de
    plazo legal, donde un día de margen es irrelevante). Degradable: la adjudicación manual desde Portal
    Empresa sigue funcionando igual si el Scheduler no está disponible."""
    try:
        from src.services import scheduler
        scheduler.registrar("b2b_rfq_cierre", lambda: cerrar_rfq_vencidas())
        scheduler.registrar_job("b2b_rfq_cierre", intervalo_horas=1,
                                descripcion="Smart Suppliers: cierre/adjudicación automática de RFQ "
                                           "vencidas")
    except Exception as e:
        logger.debug("registrar_jobs_rfq: %s", e)
