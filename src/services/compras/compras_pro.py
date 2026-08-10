"""
Compras PRO (Módulo 3, enriquecimiento). Añade lo que faltaba tras la auditoría:
  · pedidos recurrentes (programación periódica → genera pedidos reutilizando db.compras.crear_pedido),
  · órdenes abiertas / blanket orders (con consumos/call-offs que generan pedidos),
  · comparativa automática de proveedores por artículo (reutiliza precios negociados + evaluaciones +
    lead time existentes),
  · aprobación multinivel (reutiliza el Workflow existente: iniciar_proceso / aprobado).
No duplica lógica: planificación/sugerencias/recepción/consolidación ya existen (reabastecimiento,
db.compras). Auditado y multiempresa.
"""

import datetime as _dt
import json
import logging

logger = logging.getLogger("compras.pro")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III.3): la resolución de empresa pasa por la capa de identidad (Strangler).
    try:
        from src.services.compras.identidad_compras import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="compras_pedidos_recurrentes"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("compras", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Pedidos recurrentes ─────────────────────────────────────────────────────
def crear_recurrente(id_proveedor, lineas, *, nombre=None, frecuencia_dias=30, id_almacen=None,
                     proximo=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    proximo = proximo or _dt.date.today().isoformat()
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO compras_pedidos_recurrentes (id_empresa, id_proveedor, nombre, "
                        "frecuencia_dias, proximo, lineas_json, id_almacen) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_proveedor, nombre, int(frecuencia_dias), proximo,
                         json.dumps(lineas or []), id_almacen))
            rid = cur.lastrowid
            c.commit()
        _audit("PEDIDO_RECURRENTE_ALTA", f"{rid}:prov{id_proveedor}/{frecuencia_dias}d")
        return rid
    except Exception as e:
        logger.error("crear_recurrente: %s", e)
        return None


def listar_recurrentes(id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM compras_pedidos_recurrentes WHERE id_empresa<=>%s ORDER BY proximo",
                        (emp,))
            return _filas(cur)
    except Exception as e:
        logger.error("listar_recurrentes: %s", e)
        return []


def _job_recurrentes(id_empresa=None) -> str:
    """Job Scheduler: genera los pedidos recurrentes cuyo `proximo` ha vencido, reutilizando
    db.compras.crear_pedido, y reprograma. Best-effort."""
    emp = _emp(id_empresa)
    hoy = _dt.date.today()
    generados = 0
    try:
        from src.db import compras
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM compras_pedidos_recurrentes WHERE id_empresa<=>%s AND activo=1 "
                        "AND (proximo IS NULL OR proximo<=%s)", (emp, hoy.isoformat()))
            debidos = _filas(cur)
        for r in debidos:
            try:
                lineas = json.loads(r.get("lineas_json") or "[]")
            except Exception:
                lineas = []
            pid = compras.crear_pedido(r["id_proveedor"], lineas=lineas, id_almacen=r.get("id_almacen"),
                                       observaciones=f"[recurrente {r['id']}]", id_empresa=emp)
            if pid:
                generados += 1
                nuevo = (hoy + _dt.timedelta(days=int(r.get("frecuencia_dias") or 30))).isoformat()
                with obtener_conexion() as c, c.cursor() as cur:
                    cur.execute("UPDATE compras_pedidos_recurrentes SET ultimo_generado=%s, proximo=%s "
                                "WHERE id=%s", (hoy.isoformat(), nuevo, r["id"]))
                    c.commit()
    except Exception as e:
        logger.debug("_job_recurrentes: %s", e)
    _audit("PEDIDOS_RECURRENTES_JOB", f"generados={generados}")
    return f"pedidos recurrentes generados={generados}"


# ── Órdenes abiertas / blanket orders ───────────────────────────────────────
def crear_orden_abierta(id_proveedor, codigo_articulo, cantidad_total, *, precio=0, fecha_inicio=None,
                        fecha_fin=None, referencia=None, id_acuerdo=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO compras_ordenes_abiertas (id_empresa, id_proveedor, referencia, "
                        "codigo_articulo, cantidad_total, precio, fecha_inicio, fecha_fin, id_acuerdo) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_proveedor, referencia, codigo_articulo, float(cantidad_total),
                         float(precio or 0), fecha_inicio, fecha_fin, id_acuerdo))
            oid = cur.lastrowid
            c.commit()
        _audit("ORDEN_ABIERTA_ALTA", f"{oid}:prov{id_proveedor}/{codigo_articulo}", "compras_ordenes_abiertas")
        return oid
    except Exception as e:
        logger.error("crear_orden_abierta: %s", e)
        return None


def consumir_orden_abierta(id_orden, cantidad, *, id_almacen=None, usuario=None, id_empresa=None) -> dict:
    """Consume (call-off) cantidad de una orden abierta: genera un pedido por esa cantidad (reutiliza
    db.compras.crear_pedido) y actualiza lo consumido. Cierra la orden si se agota."""
    emp = _emp(id_empresa)
    try:
        from src.db import compras
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM compras_ordenes_abiertas WHERE id=%s AND id_empresa<=>%s",
                        (id_orden, emp))
            r = cur.fetchone()
            if not r:
                return {"ok": False, "motivo": "orden inexistente"}
            o = r if isinstance(r, dict) else dict(zip([x[0] for x in cur.description], r))
        restante = float(o["cantidad_total"]) - float(o["cantidad_consumida"])
        if cantidad > restante:
            return {"ok": False, "motivo": f"excede lo pendiente ({restante})"}
        pid = compras.crear_pedido(o["id_proveedor"],
                                   lineas=[{"codigo": o["codigo_articulo"], "descripcion": "call-off",
                                            "cantidad": cantidad, "precio_unitario": float(o["precio"] or 0)}],
                                   id_almacen=id_almacen, observaciones=f"[orden abierta {id_orden}]",
                                   usuario=usuario, id_empresa=emp)
        nueva_consumida = float(o["cantidad_consumida"]) + float(cantidad)
        estado = "cerrada" if nueva_consumida >= float(o["cantidad_total"]) else "abierta"
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE compras_ordenes_abiertas SET cantidad_consumida=%s, estado=%s WHERE id=%s",
                        (nueva_consumida, estado, id_orden))
            c.commit()
        _audit("ORDEN_ABIERTA_CONSUMO", f"{id_orden}:+{cantidad}->pedido{pid}", "compras_ordenes_abiertas")
        return {"ok": True, "id_pedido": pid, "consumido": nueva_consumida, "estado": estado}
    except Exception as e:
        logger.error("consumir_orden_abierta: %s", e)
        return {"ok": False, "motivo": str(e)}


def ordenes_abiertas(id_empresa=None, *, id_proveedor=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = "SELECT * FROM compras_ordenes_abiertas WHERE id_empresa<=>%s"
            p = [emp]
            if id_proveedor:
                q += " AND id_proveedor=%s"; p.append(id_proveedor)
            q += " ORDER BY creada DESC"
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("ordenes_abiertas: %s", e)
        return []


# ── Comparativa automática de proveedores ───────────────────────────────────
def comparativa_proveedores(codigo_articulo, *, id_empresa=None) -> list:
    """Compara los proveedores que ofrecen un artículo por precio negociado vigente, valoración global
    (proveedores_evaluacion) y lead time (ficha de proveedor). Devuelve una recomendación ordenada.
    Reutiliza los datos existentes; no recalcula ni duplica."""
    emp = _emp(id_empresa)
    out = []
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT DISTINCT id_proveedor, precio, descuento FROM proveedor_precios_negociados "
                        "WHERE id_empresa<=>%s AND codigo_articulo=%s "
                        "AND (fecha_fin IS NULL OR fecha_fin>=CURDATE())", (emp, codigo_articulo))
            precios = {int(f["id_proveedor"]): f for f in _filas(cur)}
            for pid, pr in precios.items():
                cur.execute("SELECT razon_social, lead_time_dias FROM proveedores WHERE id_proveedor=%s", (pid,))
                pv = cur.fetchone()
                d = pv if isinstance(pv, dict) else (dict(zip([x[0] for x in cur.description], pv)) if pv else {})
                cur.execute("SELECT AVG(valoracion_global) v FROM proveedores_evaluacion "
                            "WHERE id_empresa<=>%s AND id_proveedor=%s", (emp, pid))
                ev = cur.fetchone()
                val = float((ev[0] if not isinstance(ev, dict) else list(ev.values())[0]) or 0) if ev else 0
                precio_neto = float(pr["precio"]) * (1 - float(pr.get("descuento") or 0) / 100)
                out.append({"id_proveedor": pid, "proveedor": d.get("razon_social"),
                            "precio_neto": round(precio_neto, 4), "valoracion": round(val, 2),
                            "lead_time_dias": d.get("lead_time_dias")})
    except Exception as e:
        logger.error("comparativa_proveedores: %s", e)
    # Ordena: menor precio, mayor valoración, menor lead time.
    out.sort(key=lambda x: (x["precio_neto"], -x["valoracion"], x["lead_time_dias"] or 999))
    for i, o in enumerate(out):
        o["recomendado"] = (i == 0)
    return out


# ── Aprobación multinivel (reutiliza el Workflow existente) ─────────────────
_UMBRAL_APROBACION = 3000.0   # importe a partir del cual se exige aprobación (configurable)


def solicitar_aprobacion_pedido(id_pedido, importe, *, actor=None, id_empresa=None) -> dict:
    """Inicia el flujo de aprobación multinivel de un pedido de compra REUTILIZANDO el Workflow
    (iniciar_proceso). Los importes bajo el umbral no requieren aprobación."""
    emp = _emp(id_empresa)
    if float(importe or 0) < _UMBRAL_APROBACION:
        return {"ok": True, "requiere_aprobacion": False}
    try:
        from src.services.workflow import workflow_engine
        r = workflow_engine.iniciar_proceso("compra_pedido", id_pedido,
                                            contexto={"importe": float(importe)}, actor=actor,
                                            id_empresa=emp)
        _audit("PEDIDO_APROBACION_SOLICITADA", f"pedido={id_pedido} importe={importe}")
        return {"ok": True, "requiere_aprobacion": True, "workflow": r}
    except Exception as e:
        logger.error("solicitar_aprobacion_pedido: %s", e)
        return {"ok": False, "motivo": str(e)}


def pedido_aprobado(id_pedido, *, id_empresa=None) -> bool:
    """True si el pedido no requiere aprobación o ya está aprobado en el Workflow."""
    try:
        from src.services.workflow import workflow_engine
        return bool(workflow_engine.aprobado("compra_pedido", id_pedido))
    except Exception:
        return True   # sin workflow → comportamiento legacy (permitido)


def registrar_jobs_compras(id_empresa=None):
    """Registra el job de pedidos recurrentes en el Scheduler existente (idempotente)."""
    try:
        from src.services import scheduler
        scheduler.registrar("compras_recurrentes", _job_recurrentes)
        scheduler.registrar_job("compras_recurrentes", intervalo_horas=24,
                                descripcion="Generación de pedidos de compra recurrentes",
                                id_empresa=id_empresa)
    except Exception as e:
        logger.debug("registrar_jobs_compras: %s", e)
