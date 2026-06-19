"""
Plan de cuentas, configuración y ejercicios (E6.1).

Activación por empresa (clona el PGC PYMES), CRUD de cuentas y gestión de ejercicios.
Multiempresa por id_empresa (TenantContext). Tablas: migración C4 0013.
"""

import datetime as _dt
import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _fila_a_dict, _filas_a_dicts,
                             ensure_schema, obtener_conexion, transaccion)
from src.services.contabilidad.plan_pgc import CUENTAS_PGC

logger = logging.getLogger("contab.cuentas")


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


# ── Configuración ────────────────────────────────────────────────────────────
def obtener_config(id_empresa=None) -> dict:
    id_empresa = _empresa(id_empresa)
    base = {"id_empresa": id_empresa, "activo": 0, "plan": "pgc_pymes",
            "estrategia_posting": "cola_diaria", "ejercicio_actual": None}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM contab_config WHERE id_empresa=%s", (id_empresa,))
            r = _fila_a_dict(cur, cur.fetchone())
            if r:
                base.update({k: r.get(k) for k in base if r.get(k) is not None})
    except Exception as e:
        logger.error("obtener_config: %s", e)
    return base


def guardar_config(id_empresa=None, **campos) -> bool:
    id_empresa = _empresa(id_empresa)
    a = obtener_config(id_empresa)
    n = {k: campos.get(k, a.get(k)) for k in ("activo", "plan", "estrategia_posting",
                                              "ejercicio_actual")}
    n["activo"] = int(n["activo"] or 0)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO contab_config (id_empresa, activo, plan, estrategia_posting, "
                "ejercicio_actual) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "activo=VALUES(activo), plan=VALUES(plan), "
                "estrategia_posting=VALUES(estrategia_posting), ejercicio_actual=VALUES(ejercicio_actual)",
                (id_empresa, n["activo"], n["plan"], n["estrategia_posting"], n["ejercicio_actual"]))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_config: %s", e)
        return False


def contabilidad_activa(id_empresa=None) -> bool:
    return bool(obtener_config(id_empresa).get("activo"))


# ── Activación: clona el plan + crea ejercicio + activa ──────────────────────
def activar(id_empresa=None, anio=None) -> bool:
    """Activa la contabilidad para la empresa: clona el PGC PYMES (si no hay cuentas),
    abre el ejercicio del año indicado y marca activo=1. Idempotente."""
    id_empresa = _empresa(id_empresa)
    anio = anio or _dt.date.today().year
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM contab_cuentas WHERE id_empresa=%s", (id_empresa,))
            n = cur.fetchone()
            n = n[0] if not isinstance(n, dict) else list(n.values())[0]
            if not n:
                for codigo, nombre, tipo, nat in CUENTAS_PGC:
                    cur.execute(
                        "INSERT INTO contab_cuentas (id_empresa, codigo, nombre, grupo, tipo, "
                        "naturaleza, admite_apuntes) VALUES (%s,%s,%s,%s,%s,%s,1)",
                        (id_empresa, codigo, nombre, int(codigo[0]), tipo, nat))
            cur.execute("INSERT IGNORE INTO contab_ejercicios (id_empresa, anio, fecha_inicio, "
                        "fecha_fin) VALUES (%s,%s,%s,%s)",
                        (id_empresa, anio, f"{anio}-01-01", f"{anio}-12-31"))
        guardar_config(id_empresa, activo=1, ejercicio_actual=anio)
        logger.info("Contabilidad activada (empresa=%s, ejercicio=%s)", id_empresa, anio)
        return True
    except Exception as e:
        logger.error("activar contabilidad: %s", e)
        return False


# ── Ejercicios ───────────────────────────────────────────────────────────────
def crear_ejercicio(anio, id_empresa=None) -> bool:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO contab_ejercicios (id_empresa, anio, fecha_inicio, "
                        "fecha_fin) VALUES (%s,%s,%s,%s)",
                        (id_empresa, anio, f"{anio}-01-01", f"{anio}-12-31"))
            conn.commit()
        return True
    except Exception as e:
        logger.error("crear_ejercicio(%s): %s", anio, e)
        return False


def listar_ejercicios(id_empresa=None) -> list:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM contab_ejercicios WHERE id_empresa=%s ORDER BY anio DESC",
                        (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_ejercicios: %s", e)
        return []


def obtener_ejercicio(anio, id_empresa=None) -> dict | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM contab_ejercicios WHERE id_empresa=%s AND anio=%s",
                        (id_empresa, anio))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_ejercicio(%s): %s", anio, e)
        return None


def ejercicio_cerrado(anio, id_empresa=None) -> bool:
    ej = obtener_ejercicio(anio, id_empresa)
    return bool(ej and ej.get("estado") == "cerrado")


def cerrar_ejercicio(anio, id_empresa=None) -> bool:
    """Cierra el ejercicio (bloquea asientos). v1: marca estado=cerrado + fecha. El
    asiento formal de regularización/cierre PGC queda para una fase posterior."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE contab_ejercicios SET estado='cerrado', fecha_cierre=NOW() "
                        "WHERE id_empresa=%s AND anio=%s AND estado='abierto'", (id_empresa, anio))
            ok = cur.rowcount > 0
            conn.commit()
        return ok
    except Exception as e:
        logger.error("cerrar_ejercicio(%s): %s", anio, e)
        return False


# ── Cuentas (CRUD) ───────────────────────────────────────────────────────────
def crear_cuenta(codigo, nombre, tipo="otro", naturaleza="deudora", id_empresa=None) -> bool:
    id_empresa = _empresa(id_empresa)
    if not (codigo or "").strip():
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO contab_cuentas (id_empresa, codigo, nombre, grupo, tipo, naturaleza) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (id_empresa, codigo.strip(), nombre, int(str(codigo).strip()[0]) if codigo[0].isdigit() else 0,
                 tipo, naturaleza))
            conn.commit()
        return True
    except Exception as e:
        logger.error("crear_cuenta(%s): %s", codigo, e)
        return False


def actualizar_cuenta(codigo, id_empresa=None, **campos) -> bool:
    id_empresa = _empresa(id_empresa)
    permitidos = ("nombre", "tipo", "naturaleza", "estado", "admite_apuntes")
    sets = {k: campos[k] for k in permitidos if k in campos}
    if not sets:
        return False
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE contab_cuentas SET {cols} WHERE id_empresa=%s AND codigo=%s",
                        (*sets.values(), id_empresa, codigo))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("actualizar_cuenta(%s): %s", codigo, e)
        return False


def obtener_cuenta(codigo, id_empresa=None) -> dict | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM contab_cuentas WHERE id_empresa=%s AND codigo=%s",
                        (id_empresa, codigo))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_cuenta(%s): %s", codigo, e)
        return None


def listar_cuentas(id_empresa=None, grupo=None, texto=None) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if grupo:
        filtros.append("grupo=%s"); params.append(int(grupo))
    if texto:
        filtros.append("(codigo LIKE %s OR nombre LIKE %s)"); params += [f"%{texto}%", f"%{texto}%"]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM contab_cuentas WHERE " + " AND ".join(filtros)
                        + " ORDER BY codigo", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_cuentas: %s", e)
        return []
