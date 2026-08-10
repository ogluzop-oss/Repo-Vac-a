"""
Contratos PRO (Módulo 9, enriquecimiento). Añade SOLO lo ausente tras la auditoría:
  · Repositorio CENTRAL de contratos (proveedor/alquiler/seguro/licencia/servicio general) para los
    tipos no cubiertos por `rrhh_contratos` (laboral) ni `contratos_servicio` (cliente+SLA).
  · Obligaciones/hitos y cláusulas GENÉRICAS aplicables a cualquier contrato (origen_tipo+origen_id).
  · Alertas de vencimiento/renovación (unifica los tres repositorios) + job de scheduler.
Referencia (no reescribe) los contratos existentes. Multiempresa, auditado. Sin duplicación.
"""

import datetime as _dt
import logging

logger = logging.getLogger("contratos.pro")

TIPOS = ("proveedor", "cliente", "alquiler", "seguro", "licencia", "servicio", "laboral", "otro")
ESTADOS = ("BORRADOR", "VIGENTE", "SUSPENDIDO", "VENCIDO", "RENOVADO", "RESCINDIDO")


def _emp(id_empresa=None):
    # IOC v3 (Bloque V): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.contratos.identidad_contratos import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="contratos"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("contratos", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Repositorio central ──────────────────────────────────────────────────────
def crear_contrato(*, codigo=None, tipo="servicio", contraparte=None, id_referencia=None,
                   fecha_inicio=None, fecha_fin=None, valor=0, moneda="EUR", auto_renovacion=False,
                   preaviso_dias=30, doc_ruta=None, observaciones=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    if tipo not in TIPOS:
        tipo = "otro"
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO contratos (id_empresa, codigo, tipo, contraparte, id_referencia, "
                        "fecha_inicio, fecha_fin, valor, moneda, auto_renovacion, preaviso_dias, "
                        "doc_ruta, observaciones) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, codigo, tipo, contraparte,
                         str(id_referencia) if id_referencia is not None else None,
                         fecha_inicio, fecha_fin, float(valor or 0), moneda,
                         1 if auto_renovacion else 0, int(preaviso_dias or 30), doc_ruta, observaciones))
            cid = cur.lastrowid
            c.commit()
        _audit("CONTRATO_ALTA", f"{cid}:{tipo} {contraparte}")
        return cid
    except Exception as e:
        logger.error("crear_contrato: %s", e)
        return None


def cambiar_estado(id_contrato, estado, *, id_empresa=None) -> dict:
    if estado not in ESTADOS:
        return {"ok": False, "motivo": "estado inválido"}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE contratos SET estado=%s, actualizado=NOW() WHERE id=%s", (estado, id_contrato))
            c.commit()
        _audit("CONTRATO_ESTADO", f"{id_contrato}:{estado}")
        return {"ok": True}
    except Exception as e:
        logger.error("cambiar_estado: %s", e)
        return {"ok": False, "motivo": str(e)}


def renovar_contrato(id_contrato, *, nueva_fecha_fin=None, meses=12, id_empresa=None) -> dict:
    """Renueva un contrato: marca el actual RENOVADO y crea uno nuevo VIGENTE con las mismas condiciones."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id_empresa, codigo, tipo, contraparte, id_referencia, fecha_fin, valor, "
                        "moneda, auto_renovacion, preaviso_dias FROM contratos WHERE id=%s", (id_contrato,))
            r = cur.fetchone()
            if not r:
                return {"ok": False, "motivo": "no existe"}
            r = r if not isinstance(r, dict) else list(r.values())
            ini = r[5] or _dt.date.today()
            if isinstance(ini, str):
                try: ini = _dt.date.fromisoformat(ini)
                except Exception: ini = _dt.date.today()
            fin = nueva_fecha_fin or (ini + _dt.timedelta(days=int(meses) * 30)).isoformat()
            cur.execute("UPDATE contratos SET estado='RENOVADO', actualizado=NOW() WHERE id=%s", (id_contrato,))
            cur.execute("INSERT INTO contratos (id_empresa, codigo, tipo, contraparte, id_referencia, "
                        "fecha_inicio, fecha_fin, valor, moneda, auto_renovacion, preaviso_dias, estado) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'VIGENTE')",
                        (r[0], r[1], r[2], r[3], r[4], (r[5] or _dt.date.today()), fin,
                         r[6], r[7], r[8], r[9]))
            nid = cur.lastrowid
            c.commit()
        _audit("CONTRATO_RENOVADO", f"{id_contrato}->{nid}")
        return {"ok": True, "id_nuevo": nid, "fecha_fin": fin}
    except Exception as e:
        logger.error("renovar_contrato: %s", e)
        return {"ok": False, "motivo": str(e)}


def listar_contratos(id_empresa=None, *, tipo=None, estado=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = "SELECT * FROM contratos WHERE id_empresa<=>%s"; p = [emp]
            if tipo:
                q += " AND tipo=%s"; p.append(tipo)
            if estado:
                q += " AND estado=%s"; p.append(estado)
            q += " ORDER BY COALESCE(fecha_fin, creado) DESC"
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("listar_contratos: %s", e)
        return []


# ── Obligaciones / hitos ─────────────────────────────────────────────────────
def registrar_obligacion(origen_id, descripcion, *, origen_tipo="contratos", tipo="hito",
                         fecha_limite=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO contrato_obligaciones (id_empresa, origen_tipo, origen_id, "
                        "descripcion, tipo, fecha_limite) VALUES (%s,%s,%s,%s,%s,%s)",
                        (emp, origen_tipo, origen_id, descripcion[:255], tipo, fecha_limite))
            oid = cur.lastrowid
            c.commit()
        _audit("OBLIGACION_ALTA", f"{oid}:{origen_tipo}{origen_id}", "contrato_obligaciones")
        return oid
    except Exception as e:
        logger.error("registrar_obligacion: %s", e)
        return None


def cumplir_obligacion(id_obligacion) -> dict:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE contrato_obligaciones SET cumplida=1, fecha_cumplida=NOW() WHERE id=%s",
                        (id_obligacion,))
            c.commit()
        return {"ok": True}
    except Exception as e:
        logger.error("cumplir_obligacion: %s", e)
        return {"ok": False, "motivo": str(e)}


def obligaciones(origen_id, *, origen_tipo="contratos", solo_pendientes=False, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = ("SELECT * FROM contrato_obligaciones WHERE id_empresa<=>%s AND origen_tipo=%s "
                 "AND origen_id=%s")
            p = [emp, origen_tipo, origen_id]
            if solo_pendientes:
                q += " AND cumplida=0"
            q += " ORDER BY COALESCE(fecha_limite, creado)"
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("obligaciones: %s", e)
        return []


def anadir_clausula(origen_id, titulo, texto=None, *, origen_tipo="contratos", id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO contrato_clausulas (id_empresa, origen_tipo, origen_id, titulo, texto) "
                        "VALUES (%s,%s,%s,%s,%s)", (emp, origen_tipo, origen_id, titulo[:160], texto))
            clid = cur.lastrowid
            c.commit()
        return clid
    except Exception as e:
        logger.error("anadir_clausula: %s", e)
        return None


def clausulas(origen_id, *, origen_tipo="contratos", id_empresa=None) -> list:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM contrato_clausulas WHERE origen_tipo=%s AND origen_id=%s ORDER BY id",
                        (origen_tipo, origen_id))
            return _filas(cur)
    except Exception as e:
        logger.error("clausulas: %s", e)
        return []


# ── Alertas de vencimiento (unifica los 3 repositorios) ──────────────────────
def proximos_vencimientos(id_empresa=None, *, dias=60) -> list:
    """Contratos que vencen en los próximos `dias` — unificando repositorio central + servicio + laboral."""
    emp = _emp(id_empresa)
    limite = (_dt.date.today() + _dt.timedelta(days=int(dias))).isoformat()
    hoy = _dt.date.today().isoformat()
    salida = []
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id, codigo, tipo, contraparte, fecha_fin, auto_renovacion, preaviso_dias "
                        "FROM contratos WHERE id_empresa<=>%s AND estado='VIGENTE' AND fecha_fin IS NOT NULL "
                        "AND fecha_fin BETWEEN %s AND %s", (emp, hoy, limite))
            for r in _filas(cur):
                r["origen"] = "contratos"; salida.append(r)
            for tabla, campo in (("contratos_servicio", "fecha_fin"), ("rrhh_contratos", "fecha_fin")):
                try:
                    cur.execute(f"SELECT id, {campo} AS fecha_fin FROM {tabla} WHERE id_empresa<=>%s "
                                f"AND {campo} IS NOT NULL AND {campo} BETWEEN %s AND %s",
                                (emp, hoy, limite))
                    for r in _filas(cur):
                        r["origen"] = tabla; salida.append(r)
                except Exception:
                    pass
        return sorted(salida, key=lambda x: str(x.get("fecha_fin")))
    except Exception as e:
        logger.error("proximos_vencimientos: %s", e)
        return salida


def _job_alertas_contratos(id_empresa=None) -> dict:
    """Job de scheduler: notifica los contratos próximos a vencer (respeta preaviso)."""
    emp = _emp(id_empresa)
    venc = proximos_vencimientos(emp, dias=60)
    if not venc:
        return {"avisos": 0}
    try:
        from src.services.comunicaciones import notificaciones
        notificaciones.emitir("contrato_vencimiento", "Contratos próximos a vencer",
                              f"{len(venc)} contrato(s) vencen en los próximos 60 días.",
                              prioridad="alta", modulo="contratos",
                              roles=["ADMINISTRADOR", "GERENTE"], id_empresa=emp)
    except Exception as e:
        logger.debug("notificar vencimientos: %s", e)
    return {"avisos": len(venc)}


def registrar_jobs_contratos(id_empresa=None):
    """Registra el job de alertas en el scheduler (llamado por el JobRegistry)."""
    try:
        from src.services import scheduler
        scheduler.registrar("contratos_alertas_vencimiento", _job_alertas_contratos)
        scheduler.registrar_job("contratos_alertas_vencimiento", intervalo_horas=24,
                                descripcion="Alerta de contratos próximos a vencer")
    except Exception as e:
        logger.debug("registrar_jobs_contratos: %s", e)
