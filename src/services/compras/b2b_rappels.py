"""
Rappels acumulados / rebates de fin de año (Smart Suppliers B2B · Punto 1). Rebate RETROACTIVO sobre
el gasto acumulado con un suministrador B2B en una ventana de fechas (p.ej. el ejercicio fiscal):
superado un umbral de gasto, se abona un % sobre TODO lo acumulado en la ventana, no solo sobre la
parte que excede el umbral — así lo especifica el ejemplo original (">100.000€ = 5% rebate
retroactivo").

Nomenclatura deliberada — NO se usa "rappel"/"escalones" a secas porque ya existen dos conceptos
homónimos e inertes/distintos en el código: `proveedores.condiciones_comerciales` tiene una columna
plana `rappel` (%) que ningún cálculo real lee, y `b2b_catalogo_escalones`
(`services.compras.b2b_catalogo.guardar_escalones/escalones_de`) son descuentos por CANTIDAD dentro de
un pedido concreto — un concepto por artículo y en el momento de compra, no un rebate acumulado por
periodo. `rappel_tramos`/`rappel_liquidaciones` (migración 0258) son nombres compuestos para no
colisionar con ninguno de los dos; la UI aclara la diferencia frente a los escalones de precio por
cantidad que el proveedor ya gestiona en su catálogo.

Reutiliza, sin modificarlos, motores ya existentes:
  - `transaccion_comercial` (motor único de transacciones, `services.comercio_digital.transacciones`)
    como fuente del gasto acumulado — mismo patrón exacto que
    `services.compras.b2b_presupuesto.gasto_validado_mes` (mismo `_ESTADOS_VALIDADOS`, importado de
    ahí en vez de redefinido), pero filtrado por `id_suministrador` y con ventana de fechas abierta en
    vez de "mes en curso" fijo.
  - `db.compras.registrar_abono` (nota de abono de proveedor YA EN PRODUCCIÓN, contabilizada vía
    `contabilidad.posting.encolar_compra`) como mecanismo de liquidación — la custodia de fondos
    (`b2b_escrow`) NO sirve aquí: está anclada 1:1 a un `id_tx` de pedido, sin ningún concepto de saldo
    acumulado empresa↔proveedor; forzarlo ahí exigiría inventar una tabla paralela de todos modos.
  - `proveedores.id_suministrador` (migración 0218) como puente para resolver el `id_proveedor`
    tradicional que `registrar_abono` necesita a partir de un `id_suministrador` B2B.

Idempotencia de `liquidar_rappel`: ver docstring de la migración 0258 (`UNIQUE KEY uq_rl_ventana` +
patrón "reclamar placeholder → calcular → completar").
"""

import datetime as _dt
import logging

from src.db.conexion import ensure_schema, obtener_conexion, transaccion
from src.services.compras.b2b_presupuesto import _ESTADOS_VALIDADOS

logger = logging.getLogger("compras.b2b_rappels")

ESTADOS_TRAMO = ("activo", "inactivo")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _filas(cur):
    cols = [d[0] for d in cur.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]


def _iso(d):
    """Normaliza DATE (string 'YYYY-MM-DD' o `datetime.date` leído de pymysql) a string ISO
    comparable lexicográficamente."""
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("compras.b2b_rappels", accion, "rappel_tramos", (detalle or "")[:255])
    except Exception:
        pass


# ── Tramos ─────────────────────────────────────────────────────────────────────
def crear_tramo(id_empresa, id_suministrador, umbral_desde, pct_rebate, fecha_inicio, fecha_fin,
                creado_por=None) -> int | None:
    """Da de alta un tramo de rebate retroactivo para (empresa, suministrador). `fecha_inicio`/
    `fecha_fin` acotan la ventana del acuerdo (p.ej. el ejercicio fiscal)."""
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rappel_tramos (id_empresa, id_suministrador, umbral_desde, pct_rebate, "
                "fecha_inicio, fecha_fin, creado_por) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_suministrador, round(float(umbral_desde or 0), 2),
                 round(float(pct_rebate or 0), 2), fecha_inicio, fecha_fin, creado_por))
            tid = cur.lastrowid
        _audit("TRAMO_ALTA", f"{tid}:emp={id_empresa} sum={id_suministrador} "
                             f">={umbral_desde}={pct_rebate}%")
        return tid
    except Exception as e:
        logger.error("crear_tramo(%s,%s): %s", id_empresa, id_suministrador, e)
        return None


def listar_tramos(id_empresa=None, id_suministrador=None) -> list:
    """Tramos configurados, opcionalmente filtrados por empresa y/o suministrador. Con solo
    `id_suministrador` (sin `id_empresa`) devuelve los tramos que CUALQUIER empresa le haya
    configurado a ese suministrador — es la consulta que usa su vista de solo-progreso en Portal
    Proveedor, donde no hay una única empresa de sesión."""
    try:
        ensure_schema()
        filtros, params = [], []
        if id_empresa:
            filtros.append("id_empresa=%s"); params.append(id_empresa)
        if id_suministrador:
            filtros.append("id_suministrador=%s"); params.append(id_suministrador)
        where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM rappel_tramos {where} "
                        f"ORDER BY id_empresa, id_suministrador, umbral_desde DESC", params)
            return _filas(cur)
    except Exception as e:
        logger.error("listar_tramos(%s,%s): %s", id_empresa, id_suministrador, e)
        return []


def _tramos_vigentes_ventana(id_empresa, id_suministrador, fecha_inicio, fecha_fin) -> list:
    """Tramos activos cuya vigencia se solapa con la ventana de liquidación pedida."""
    fi, ff = _iso(fecha_inicio), _iso(fecha_fin)
    return [t for t in listar_tramos(id_empresa, id_suministrador)
            if (t.get("estado") or "activo") == "activo"
            and _iso(t["fecha_inicio"]) <= ff and _iso(t["fecha_fin"]) >= fi]


# ── Cálculo ──────────────────────────────────────────────────────────────────
def gasto_acumulado(id_empresa, id_suministrador, fecha_inicio, fecha_fin) -> float:
    """Suma de `total` de transacciones B2B validadas (mismo `_ESTADOS_VALIDADOS` que
    `b2b_presupuesto.gasto_validado_mes`) de ese suministrador, dentro de la ventana de fechas."""
    try:
        ensure_schema()
        placeholders = ",".join(["%s"] * len(_ESTADOS_VALIDADOS))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT COALESCE(SUM(total),0) FROM transaccion_comercial WHERE id_empresa=%s "
                f"AND id_suministrador=%s AND origen='b2b' AND estado IN ({placeholders}) "
                f"AND DATE(creada) BETWEEN %s AND %s",
                (id_empresa, id_suministrador, *_ESTADOS_VALIDADOS, fecha_inicio, fecha_fin))
            row = cur.fetchone()
            v = row[0] if not isinstance(row, dict) else list(row.values())[0]
            return float(v or 0)
    except Exception as e:
        logger.error("gasto_acumulado(%s,%s): %s", id_empresa, id_suministrador, e)
        return 0.0


def tramo_alcanzado(gasto, tramos) -> dict | None:
    """El tramo de umbral más alto alcanzado por `gasto`, entre los `tramos` dados (ya filtrados por
    el llamante — activos y vigentes en la ventana, ver `_tramos_vigentes_ventana`)."""
    candidatos = [t for t in (tramos or []) if float(t.get("umbral_desde") or 0) <= float(gasto or 0)]
    if not candidatos:
        return None
    return max(candidatos, key=lambda t: float(t.get("umbral_desde") or 0))


def rebate_estimado(gasto, tramo) -> float:
    """Rebate RETROACTIVO: % del tramo alcanzado sobre TODO el gasto acumulado (no solo la parte que
    excede el umbral) — así lo especifica el caso de uso original (">100.000€ = 5% retroactivo")."""
    if not tramo:
        return 0.0
    return round(float(gasto or 0) * float(tramo.get("pct_rebate") or 0) / 100.0, 2)


def resolver_id_proveedor(id_suministrador) -> int | None:
    """Puente `proveedores.id_suministrador` (migración 0218) → `id_proveedor` tradicional, el que
    necesita `db.compras.registrar_abono`. `None` si el suministrador B2B no está vinculado a ningún
    proveedor tradicional en esta empresa (homologación/onboarding aún no completados)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_proveedor FROM proveedores WHERE id_suministrador=%s LIMIT 1",
                       (id_suministrador,))
            row = cur.fetchone()
            if not row:
                return None
            return row[0] if not isinstance(row, dict) else row["id_proveedor"]
    except Exception as e:
        logger.error("resolver_id_proveedor(%s): %s", id_suministrador, e)
        return None


# ── Liquidaciones ────────────────────────────────────────────────────────────
def liquidacion_existente(id_empresa, id_suministrador, fecha_inicio, fecha_fin) -> dict | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM rappel_liquidaciones WHERE id_empresa=%s AND id_suministrador=%s "
                "AND fecha_inicio=%s AND fecha_fin=%s LIMIT 1",
                (id_empresa, id_suministrador, fecha_inicio, fecha_fin))
            row = cur.fetchone()
            return _fila(cur, row) if row else None
    except Exception as e:
        logger.error("liquidacion_existente(%s,%s): %s", id_empresa, id_suministrador, e)
        return None


def listar_liquidaciones(id_empresa=None, id_suministrador=None, limite=200) -> list:
    try:
        ensure_schema()
        filtros, params = [], []
        if id_empresa:
            filtros.append("id_empresa=%s"); params.append(id_empresa)
        if id_suministrador:
            filtros.append("id_suministrador=%s"); params.append(id_suministrador)
        where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM rappel_liquidaciones {where} "
                        f"ORDER BY fecha_liquidacion DESC LIMIT %s", params + [int(limite)])
            return _filas(cur)
    except Exception as e:
        logger.error("listar_liquidaciones(%s,%s): %s", id_empresa, id_suministrador, e)
        return []


def _borrar_liquidacion_placeholder(id_liq):
    """Libera la ventana reclamada si el cálculo posterior falla ANTES de contabilizar ningún abono
    (proveedor sin vincular / error registrando el abono) — nunca borra una liquidación que ya llegó a
    tener `id_factura_abono` (defensivo: WHERE explícito)."""
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM rappel_liquidaciones WHERE id=%s AND id_factura_abono IS NULL",
                       (id_liq,))
    except Exception as e:
        logger.error("_borrar_liquidacion_placeholder(%s): %s", id_liq, e)


def liquidar_rappel(id_empresa, id_suministrador, fecha_inicio, fecha_fin, usuario=None) -> dict:
    """Calcula y liquida el rappel de la ventana `(fecha_inicio, fecha_fin)` para ese
    (empresa, suministrador): gasto acumulado → tramo alcanzado → rebate retroactivo → abono real al
    proveedor (`db.compras.registrar_abono`) → registro en `rappel_liquidaciones`.

    Idempotente: si la ventana ya tiene una liquidación (fuera o en curso), se rechaza con un motivo
    explícito en vez de reintentar o duplicar el abono — ver docstring de la migración 0258 para el
    mecanismo (reclama la ventana con un INSERT amparado por `UNIQUE KEY uq_rl_ventana` ANTES de
    calcular/llamar al abono, así que una carrera entre dos llamadas nunca puede generar dos abonos).
    """
    existente = liquidacion_existente(id_empresa, id_suministrador, fecha_inicio, fecha_fin)
    if existente:
        return {"ok": False, "motivo": "ya_liquidado", "id_liquidacion": existente["id"],
                "importe_rebate": float(existente.get("importe_rebate") or 0)}

    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rappel_liquidaciones (id_empresa, id_suministrador, fecha_inicio, "
                "fecha_fin, gasto_total, pct_aplicado, importe_rebate) VALUES (%s,%s,%s,%s,0,0,0)",
                (id_empresa, id_suministrador, fecha_inicio, fecha_fin))
            id_liq = cur.lastrowid
    except Exception as e:
        logger.info("liquidar_rappel: no se pudo reclamar la ventana (probablemente ya liquidada o en "
                   "curso) (%s,%s,%s,%s): %s", id_empresa, id_suministrador, fecha_inicio, fecha_fin, e)
        return {"ok": False, "motivo": "ya_liquidado_o_en_curso"}

    gasto = gasto_acumulado(id_empresa, id_suministrador, fecha_inicio, fecha_fin)
    tramos_vig = _tramos_vigentes_ventana(id_empresa, id_suministrador, fecha_inicio, fecha_fin)
    tramo = tramo_alcanzado(gasto, tramos_vig)
    rebate = rebate_estimado(gasto, tramo)

    id_factura_abono = None
    if rebate > 0:
        id_proveedor = resolver_id_proveedor(id_suministrador)
        if not id_proveedor:
            _borrar_liquidacion_placeholder(id_liq)
            return {"ok": False, "motivo": "proveedor_no_vinculado", "gasto_total": gasto,
                    "tramo_aplicado": tramo, "importe_rebate": rebate}
        numero_ref = f"RAPPEL-{id_suministrador}-{_iso(fecha_inicio)}_{_iso(fecha_fin)}"
        try:
            from src.db import compras as C
            id_factura_abono = C.registrar_abono(
                id_proveedor=id_proveedor, numero_factura=numero_ref, base=rebate, iva=0,
                id_empresa=id_empresa, fecha_factura=_dt.date.today().isoformat())
        except Exception as e:
            logger.error("liquidar_rappel: registrar_abono (%s,%s): %s", id_empresa, id_suministrador, e)
            id_factura_abono = None
        if not id_factura_abono:
            _borrar_liquidacion_placeholder(id_liq)
            return {"ok": False, "motivo": "error_registrando_abono", "gasto_total": gasto,
                    "tramo_aplicado": tramo, "importe_rebate": rebate}

    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE rappel_liquidaciones SET gasto_total=%s, tramo_aplicado_id=%s, "
                "pct_aplicado=%s, importe_rebate=%s, id_factura_abono=%s WHERE id=%s",
                (round(gasto, 2), tramo["id"] if tramo else None,
                 float(tramo.get("pct_rebate") or 0) if tramo else 0.0, rebate, id_factura_abono, id_liq))
    except Exception as e:
        # El abono (si lo hubo) ya está contabilizado de forma real — no se revierte aquí (igual que
        # `registrar_factura`, que tampoco deshace la contabilización si un paso posterior falla). La
        # liquidación queda como placeholder (gasto_total=0), visible para revisión manual.
        logger.error("liquidar_rappel: error completando el registro de liquidación %s: %s", id_liq, e)
        return {"ok": False, "motivo": "error_completando_liquidacion", "id_liquidacion": id_liq,
                "gasto_total": gasto, "tramo_aplicado": tramo, "importe_rebate": rebate,
                "id_factura_abono": id_factura_abono}

    _audit("LIQUIDACION", f"{id_liq}:emp={id_empresa} sum={id_suministrador} "
                          f"gasto={gasto} rebate={rebate} abono={id_factura_abono}")
    return {"ok": True, "id_liquidacion": id_liq, "gasto_total": gasto, "tramo_aplicado": tramo,
            "pct_aplicado": float(tramo.get("pct_rebate") or 0) if tramo else 0.0,
            "importe_rebate": rebate, "id_factura_abono": id_factura_abono}


def progreso_suministrador(id_empresa, id_suministrador, tramos=None) -> dict:
    """Resumen para la barra de progreso neón (Portal Empresa y Portal Proveedor): gasto acumulado en
    la ventana del tramo más próximo a alcanzar (o del más alto ya alcanzado), tramo alcanzado y
    rebate estimado (aún no liquidado). Usa la ventana del PRIMER tramo de la lista (todos los tramos
    de un mismo (empresa, suministrador) comparten normalmente la misma vigencia de acuerdo)."""
    tramos = tramos if tramos is not None else listar_tramos(id_empresa, id_suministrador)
    if not tramos:
        return {"tiene_tramos": False}
    fecha_inicio = min(_iso(t["fecha_inicio"]) for t in tramos)
    fecha_fin = max(_iso(t["fecha_fin"]) for t in tramos)
    gasto = gasto_acumulado(id_empresa, id_suministrador, fecha_inicio, fecha_fin)
    vigentes = [t for t in tramos if (t.get("estado") or "activo") == "activo"]
    tramo = tramo_alcanzado(gasto, vigentes)
    rebate = rebate_estimado(gasto, tramo)
    siguiente = None
    pendientes = [t for t in vigentes if float(t["umbral_desde"]) > gasto]
    if pendientes:
        siguiente = min(pendientes, key=lambda t: float(t["umbral_desde"]))
    techo = float(siguiente["umbral_desde"]) if siguiente else (
        float(tramo["umbral_desde"]) if tramo else max((float(t["umbral_desde"]) for t in tramos), default=0))
    pct_barra = min(round(gasto / techo * 100, 1), 100) if techo else 0.0
    return {"tiene_tramos": True, "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin,
            "gasto_acumulado": round(gasto, 2), "tramo_alcanzado": tramo, "siguiente_tramo": siguiente,
            "pct_aplicado": float(tramo.get("pct_rebate") or 0) if tramo else 0.0,
            "rebate_estimado": rebate, "pct_barra": pct_barra}


# ── Job programado ───────────────────────────────────────────────────────────
def _job_liquidacion_rappels() -> dict:
    """Job de scheduler: liquida automáticamente toda ventana `(id_empresa, id_suministrador,
    fecha_inicio, fecha_fin)` cuyo `fecha_fin` ya haya pasado y que aún no tenga liquidación
    registrada. Idempotente por construcción (`liquidar_rappel`), así que reintentos del propio
    scheduler tras un fallo parcial son seguros."""
    liquidadas = fallidas = 0
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT rt.id_empresa, rt.id_suministrador, rt.fecha_inicio, rt.fecha_fin "
                "FROM rappel_tramos rt WHERE rt.estado='activo' AND rt.fecha_fin < CURDATE() "
                "AND NOT EXISTS (SELECT 1 FROM rappel_liquidaciones rl WHERE "
                "rl.id_empresa=rt.id_empresa AND rl.id_suministrador=rt.id_suministrador AND "
                "rl.fecha_inicio=rt.fecha_inicio AND rl.fecha_fin=rt.fecha_fin)")
            ventanas = _filas(cur)
    except Exception as e:
        logger.error("_job_liquidacion_rappels (consulta de ventanas vencidas): %s", e)
        return {"liquidadas": 0, "fallidas": 0, "error": str(e)}
    for v in ventanas:
        r = liquidar_rappel(v["id_empresa"], v["id_suministrador"], v["fecha_inicio"], v["fecha_fin"],
                            usuario="scheduler")
        if r.get("ok"):
            liquidadas += 1
        else:
            fallidas += 1
            logger.warning("_job_liquidacion_rappels(%s,%s,%s,%s): %s", v["id_empresa"],
                          v["id_suministrador"], v["fecha_inicio"], v["fecha_fin"], r.get("motivo"))
    return {"liquidadas": liquidadas, "fallidas": fallidas, "ventanas": len(ventanas)}


def registrar_jobs_rappels(id_empresa=None):
    """Registra el job programado de liquidación automática (mismo patrón exacto que
    `contratos_pro.registrar_jobs_contratos`/`b2b_escrow.registrar_jobs_escrow`). Degradable: si el
    Scheduler no está disponible, la liquidación manual (`liquidar_rappel` desde Portal Empresa) sigue
    funcionando igual."""
    try:
        from src.services import scheduler
        scheduler.registrar("b2b_rappels_liquidacion", lambda: _job_liquidacion_rappels())
        scheduler.registrar_job("b2b_rappels_liquidacion", intervalo_horas=24,
                                descripcion="Smart Suppliers: liquidación automática de rappels con "
                                           "ventana de acuerdo vencida")
    except Exception as e:
        logger.debug("registrar_jobs_rappels: %s", e)
