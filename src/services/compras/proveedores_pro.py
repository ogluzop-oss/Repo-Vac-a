"""
Compras · Proveedores PRO (Módulo 2, enriquecimiento). Añade lo que faltaba tras la auditoría:
certificaciones (con caducidad), acuerdos marco (con renovación) y precios negociados por artículo
(con vigencia). La RENOVACIÓN AUTOMÁTICA se resuelve con un job del Scheduler existente que alerta de
vencimientos (reutiliza notificaciones + auditoría). No duplica: homologación/evaluación/scoring ya
existen en `db/proveedores` y `proveedores_evaluacion`.
"""

import datetime as _dt
import logging

logger = logging.getLogger("compras.proveedores_pro")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III.3): la resolución de empresa pasa por la capa de identidad (Strangler).
    try:
        from src.services.compras.identidad_compras import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="proveedor_certificaciones"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("compras", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Certificaciones ─────────────────────────────────────────────────────────
def añadir_certificacion(id_proveedor, tipo, *, numero=None, emisor=None, fecha_emision=None,
                         fecha_caducidad=None, renovacion_auto=False, ref_documento=None,
                         id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO proveedor_certificaciones (id_empresa, id_proveedor, tipo, numero, "
                        "emisor, fecha_emision, fecha_caducidad, renovacion_auto, ref_documento) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_proveedor, tipo[:60], numero, emisor, fecha_emision, fecha_caducidad,
                         1 if renovacion_auto else 0, ref_documento))
            cid = cur.lastrowid
            c.commit()
        _audit("PROV_CERT_ALTA", f"{id_proveedor}:{tipo}")
        return cid
    except Exception as e:
        logger.error("añadir_certificacion: %s", e)
        return None


def certificaciones(id_proveedor, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM proveedor_certificaciones WHERE id_empresa<=>%s AND id_proveedor=%s "
                        "ORDER BY fecha_caducidad", (emp, id_proveedor))
            return _filas(cur)
    except Exception as e:
        logger.error("certificaciones: %s", e)
        return []


# ── Acuerdos marco ──────────────────────────────────────────────────────────
def crear_acuerdo_marco(id_proveedor, *, referencia=None, descripcion=None, fecha_inicio=None,
                        fecha_fin=None, importe_comprometido=0, condiciones=None,
                        renovacion_auto=False, meses_renovacion=12, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO proveedor_acuerdos_marco (id_empresa, id_proveedor, referencia, "
                        "descripcion, fecha_inicio, fecha_fin, importe_comprometido, condiciones, "
                        "renovacion_auto, meses_renovacion) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_proveedor, referencia, descripcion, fecha_inicio, fecha_fin,
                         float(importe_comprometido or 0), condiciones, 1 if renovacion_auto else 0,
                         int(meses_renovacion or 12)))
            aid = cur.lastrowid
            c.commit()
        _audit("PROV_ACUERDO_ALTA", f"{id_proveedor}:{referencia}", "proveedor_acuerdos_marco")
        return aid
    except Exception as e:
        logger.error("crear_acuerdo_marco: %s", e)
        return None


def acuerdos_marco(id_proveedor=None, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = "SELECT * FROM proveedor_acuerdos_marco WHERE id_empresa<=>%s"
            p = [emp]
            if id_proveedor:
                q += " AND id_proveedor=%s"; p.append(id_proveedor)
            q += " ORDER BY fecha_fin"
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("acuerdos_marco: %s", e)
        return []


# ── Precios negociados por artículo ─────────────────────────────────────────
def set_precio_negociado(id_proveedor, codigo_articulo, precio, *, divisa="EUR", descuento=0,
                         cantidad_minima=1, fecha_inicio=None, fecha_fin=None, id_acuerdo=None,
                         id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO proveedor_precios_negociados (id_empresa, id_proveedor, "
                        "codigo_articulo, precio, divisa, descuento, cantidad_minima, fecha_inicio, "
                        "fecha_fin, id_acuerdo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_proveedor, codigo_articulo, float(precio), divisa, float(descuento or 0),
                         int(cantidad_minima or 1), fecha_inicio, fecha_fin, id_acuerdo))
            pid = cur.lastrowid
            c.commit()
        _audit("PROV_PRECIO_NEGOCIADO", f"{id_proveedor}:{codigo_articulo}={precio}",
               "proveedor_precios_negociados")
        return pid
    except Exception as e:
        logger.error("set_precio_negociado: %s", e)
        return None


def precio_vigente(id_proveedor, codigo_articulo, *, id_empresa=None):
    """Precio negociado VIGENTE de un artículo para un proveedor (o None). Útil para pedidos/compras."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT precio, descuento, divisa FROM proveedor_precios_negociados "
                        "WHERE id_empresa<=>%s AND id_proveedor=%s AND codigo_articulo=%s "
                        "AND (fecha_inicio IS NULL OR fecha_inicio<=CURDATE()) "
                        "AND (fecha_fin IS NULL OR fecha_fin>=CURDATE()) ORDER BY creada DESC LIMIT 1",
                        (emp, id_proveedor, codigo_articulo))
            r = cur.fetchone()
            if not r:
                return None
            d = r if isinstance(r, dict) else dict(zip([x[0] for x in cur.description], r))
            return d
    except Exception as e:
        logger.debug("precio_vigente: %s", e)
        return None


# ── Renovaciones automáticas (job del Scheduler existente) ──────────────────
def vencimientos(dias=30, id_empresa=None) -> dict:
    """Certificaciones y acuerdos que caducan en los próximos `dias` (para alertar/renovar)."""
    emp = _emp(id_empresa)
    lim = (_dt.date.today() + _dt.timedelta(days=int(dias))).isoformat()
    out = {"certificaciones": [], "acuerdos": []}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM proveedor_certificaciones WHERE id_empresa<=>%s AND estado='vigente' "
                        "AND fecha_caducidad IS NOT NULL AND fecha_caducidad<=%s", (emp, lim))
            out["certificaciones"] = _filas(cur)
            cur.execute("SELECT * FROM proveedor_acuerdos_marco WHERE id_empresa<=>%s AND estado='vigente' "
                        "AND fecha_fin IS NOT NULL AND fecha_fin<=%s", (emp, lim))
            out["acuerdos"] = _filas(cur)
    except Exception as e:
        logger.debug("vencimientos: %s", e)
    return out


def _renovar_acuerdo(cur, ac):
    """Renueva un acuerdo con renovacion_auto: extiende fecha_fin `meses_renovacion` meses."""
    meses = int(ac.get("meses_renovacion") or 12)
    ff = ac.get("fecha_fin")
    if isinstance(ff, str):
        ff = _dt.date.fromisoformat(ff)
    base = ff or _dt.date.today()
    nueva = base + _dt.timedelta(days=30 * meses)
    cur.execute("UPDATE proveedor_acuerdos_marco SET fecha_fin=%s WHERE id=%s", (nueva.isoformat(), ac["id"]))


def _job_renovaciones(id_empresa=None) -> str:
    """Job Scheduler: alerta de certificaciones/acuerdos por vencer y renueva los marcados
    `renovacion_auto`. Reutiliza notificaciones + auditoría. Best-effort."""
    emp = _emp(id_empresa)
    v = vencimientos(dias=30, id_empresa=emp)
    n_cert, n_acu = len(v["certificaciones"]), len(v["acuerdos"])
    renovados = 0
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            for ac in v["acuerdos"]:
                if ac.get("renovacion_auto"):
                    _renovar_acuerdo(cur, ac); renovados += 1
            c.commit()
    except Exception as e:
        logger.debug("renovar acuerdos: %s", e)
    # Notifica los vencimientos (reutiliza el sistema de notificaciones).
    if n_cert or n_acu:
        try:
            from src.services import notificaciones
            notificaciones.emitir(
                "proveedor_vencimiento", "Proveedores: vencimientos próximos",
                f"{n_cert} certificación(es) y {n_acu} acuerdo(s) marco vencen en 30 días.",
                prioridad="alta", modulo="compras", roles=["ADMINISTRADOR", "GERENTE"], id_empresa=emp)
        except Exception as e:
            logger.debug("notificar vencimientos: %s", e)
    _audit("PROV_RENOVACIONES", f"cert={n_cert} acuerdos={n_acu} renovados={renovados}",
           "proveedor_acuerdos_marco")
    return f"vencen cert={n_cert} acuerdos={n_acu}; renovados={renovados}"


def registrar_jobs_proveedores(id_empresa=None):
    """Registra el job de renovaciones en el Scheduler existente (idempotente)."""
    try:
        from src.services import scheduler
        scheduler.registrar("proveedores_renovaciones", _job_renovaciones)
        scheduler.registrar_job("proveedores_renovaciones", intervalo_horas=24,
                                descripcion="Alertas y renovación de certificaciones/acuerdos de proveedor",
                                id_empresa=id_empresa)
    except Exception as e:
        logger.debug("registrar_jobs_proveedores: %s", e)
