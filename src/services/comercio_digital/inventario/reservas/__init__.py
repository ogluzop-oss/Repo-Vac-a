"""
PCD · Inventario · Reservation Ledger (CD-005 · Fase 5).

LIBRO CONTABLE append-only (como el Kárdex): nunca se edita/sobrescribe una reserva; cada cambio de
estado escribe una FILA nueva. Estados: SOFT_CREATED → HARD_CONFIRMED → RELEASED | CONSUMED | EXPIRED.

Contrato del dominio (ratificado):
  · ÚNICO mecanismo que reduce el ATP. Nadie más bloquea inventario (ni Fulfillment, ni Workflow, ni
    TPV, ni canales, ni Availability). Availability solo lee: on_hand − reservas activas − safety.
  · Toda reserva pertenece SIEMPRE a una Transacción (id_tx) y a una Línea (id_linea). Sin huérfanas.
  · OMNICANAL: un único ledger para todos los canales; solo cambian tipo/prioridad/TTL/reglas.
  · TTL vía Rules por CAPACIDADES (degradable; defectos soft=30min, hard=48h). NO importa Rules.
  · NO mueve stock, NO toca el Kárdex. Simple, determinista, auditable (sin IA/reasignación aún).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("cd.reservas")

FASE = 5

# Estados del ledger (libro contable). ACTIVOS = los que reducen el ATP.
SOFT_CREATED, HARD_CONFIRMED = "SOFT_CREATED", "HARD_CONFIRMED"
RELEASED, CONSUMED, EXPIRED = "RELEASED", "CONSUMED", "EXPIRED"
ESTADOS = (SOFT_CREATED, HARD_CONFIRMED, RELEASED, CONSUMED, EXPIRED)
ACTIVOS = (SOFT_CREATED, HARD_CONFIRMED)

# Transiciones válidas (append-only: cada cambio es una fila nueva; los terminales no transicionan).
_TRANSICIONES = {
    SOFT_CREATED: {HARD_CONFIRMED, RELEASED, CONSUMED, EXPIRED},
    HARD_CONFIRMED: {RELEASED, CONSUMED, EXPIRED},
    RELEASED: set(), CONSUMED: set(), EXPIRED: set(),
}

# TTL por defecto (minutos). Se puede sobreescribir por Rules (capacidades).
_TTL_DEFECTO = {"soft": 30, "hard": 48 * 60}


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
def _ttl_minutos(tipo, id_empresa, canal):
    """TTL resuelto por CAPACIDADES (Rules), degradable a los defectos. Nunca importa Rules directo."""
    try:
        from src.platform import capabilities as cap
        rules = cap.rules()
        if rules is not None and hasattr(rules, "ttl_reserva"):
            v = rules.ttl_reserva(tipo=tipo, id_empresa=id_empresa, canal=canal)
            if v:
                return int(v)
    except Exception:
        pass
    return _TTL_DEFECTO.get(tipo, _TTL_DEFECTO["soft"])


def _fila_actual(cur, id_reserva):
    """Último apunte (estado vigente) de una reserva. El ledger es append-only: MAX(id)."""
    cur.execute("SELECT id_empresa, id_tx, id_linea, codigo_articulo, bucket, cantidad, tipo, estado "
                "FROM cd_reservas WHERE id_reserva=%s ORDER BY id DESC LIMIT 1", (id_reserva,))
    r = cur.fetchone()
    if not r:
        return None
    vals = list(r.values()) if isinstance(r, dict) else list(r)
    return dict(zip(("id_empresa", "id_tx", "id_linea", "codigo_articulo", "bucket", "cantidad",
                     "tipo", "estado"), vals))


def reservar(id_tx, codigo, cantidad, bucket, *, tipo="soft", id_linea=None, id_empresa=None,
             ttl_min=None, actor=None, canal=None):
    """Crea una reserva (apunte inicial SOFT_CREATED/HARD_CONFIRMED). Devuelve id_reserva. RECHAZA
    reservas huérfanas: exige id_tx (aclaración 3). NO mueve stock."""
    if not id_tx:
        logger.warning("reserva rechazada: sin transacción (no se permiten huérfanas)")
        return None
    tipo = "hard" if str(tipo).lower() == "hard" else "soft"
    estado = HARD_CONFIRMED if tipo == "hard" else SOFT_CREATED
    emp = _emp(id_empresa)
    minutos = _ttl_minutos(tipo, emp, canal) if ttl_min is None else int(ttl_min)
    expira = datetime.now() + timedelta(minutes=minutos)
    id_reserva = str(uuid.uuid4())
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cd_reservas (id_reserva, id_empresa, id_tx, id_linea, codigo_articulo, "
                "bucket, cantidad, tipo, estado, canal, ttl_expira, actor) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_reserva, emp, id_tx, id_linea, codigo, bucket, int(cantidad), tipo, estado,
                 canal, expira, actor))
            conn.commit()
        return id_reserva
    except Exception as e:
        logger.error("reservar(%s): %s", codigo, e)
        return None


def _transicionar(id_reserva, nuevo, *, actor=None, id_empresa=None):
    """Registra un cambio de estado como APUNTE NUEVO (nunca modifica el anterior)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            actual = _fila_actual(cur, id_reserva)
            if not actual:
                return False
            if nuevo not in _TRANSICIONES.get(actual["estado"], set()):
                logger.warning("transición inválida %s→%s (reserva %s)", actual["estado"], nuevo,
                               id_reserva)
                return False
            cur.execute(
                "INSERT INTO cd_reservas (id_reserva, id_empresa, id_tx, id_linea, codigo_articulo, "
                "bucket, cantidad, tipo, estado, actor) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_reserva, actual["id_empresa"], actual["id_tx"], actual["id_linea"],
                 actual["codigo_articulo"], actual["bucket"], actual["cantidad"], actual["tipo"],
                 nuevo, actor))
            conn.commit()
            return True
    except Exception as e:
        logger.error("_transicionar(%s→%s): %s", id_reserva, nuevo, e)
        return False


def confirmar(id_reserva, *, actor=None, id_empresa=None):
    """SOFT_CREATED → HARD_CONFIRMED (p.ej. al pagar)."""
    return _transicionar(id_reserva, HARD_CONFIRMED, actor=actor, id_empresa=id_empresa)


def liberar(id_reserva, *, actor=None, id_empresa=None):
    """→ RELEASED (cancelación/abandono). Deja de reducir ATP."""
    return _transicionar(id_reserva, RELEASED, actor=actor, id_empresa=id_empresa)


def consumir(id_reserva, *, actor=None, id_empresa=None):
    """→ CONSUMED (la salida de stock la ejecuta la política única; aquí solo se cierra el apunte)."""
    return _transicionar(id_reserva, CONSUMED, actor=actor, id_empresa=id_empresa)


def expirar(id_reserva, *, actor=None, id_empresa=None):
    """→ EXPIRED (TTL vencido)."""
    return _transicionar(id_reserva, EXPIRED, actor=actor, id_empresa=id_empresa)


def estado(id_reserva):
    """Estado vigente (último apunte)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            f = _fila_actual(cur, id_reserva)
            return f["estado"] if f else None
    except Exception:
        return None


def reservado(codigo, id_empresa=None, bucket=None):
    """Cantidad ACTIVA (SOFT_CREATED/HARD_CONFIRMED vigentes) para un artículo. Es lo ÚNICO que resta
    del ATP. Determinista: refleja el estado del ledger (la caducidad la aplica el barrido)."""
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = ("SELECT COALESCE(SUM(r.cantidad),0) FROM cd_reservas r "
                   "JOIN (SELECT id_reserva, MAX(id) mid FROM cd_reservas "
                   "      WHERE id_empresa=%s AND codigo_articulo=%s GROUP BY id_reserva) x "
                   "  ON r.id=x.mid "
                   "WHERE r.estado IN ('SOFT_CREATED','HARD_CONFIRMED')")
            params = [emp, codigo]
            if bucket is not None:
                sql += " AND r.bucket=%s"
                params.append(bucket)
            cur.execute(sql, tuple(params))
            r = cur.fetchone()
            v = list(r.values())[0] if isinstance(r, dict) else r[0]
            return int(v or 0)
    except Exception as e:
        logger.error("reservado(%s): %s", codigo, e)
        return 0


def activas(id_tx=None, id_empresa=None):
    """Reservas cuyo estado vigente es ACTIVO (para una transacción o empresa)."""
    emp = _emp(id_empresa)
    out = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = ("SELECT r.id_reserva, r.codigo_articulo, r.bucket, r.cantidad, r.tipo, r.estado, "
                   "r.id_tx, r.id_linea, r.ttl_expira FROM cd_reservas r "
                   "JOIN (SELECT id_reserva, MAX(id) mid FROM cd_reservas WHERE id_empresa=%s "
                   + ("AND id_tx=%s " if id_tx else "") + "GROUP BY id_reserva) x ON r.id=x.mid "
                   "WHERE r.estado IN ('SOFT_CREATED','HARD_CONFIRMED')")
            params = [emp, id_tx] if id_tx else [emp]
            cur.execute(sql, tuple(params))
            cols = ("id_reserva", "codigo_articulo", "bucket", "cantidad", "tipo", "estado", "id_tx",
                    "id_linea", "ttl_expira")
            for f in cur.fetchall():
                vals = list(f.values()) if isinstance(f, dict) else list(f)
                out.append(dict(zip(cols, vals)))
    except Exception as e:
        logger.error("activas: %s", e)
    return out


def barrer_expiradas(id_empresa=None):
    """Barrido (Scheduler): las reservas activas con TTL vencido pasan a EXPIRED (apunte nuevo).
    Devuelve el nº de reservas expiradas. Determinista respecto al ledger + reloj."""
    emp = _emp(id_empresa)
    expiradas = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT r.id_reserva FROM cd_reservas r "
                "JOIN (SELECT id_reserva, MAX(id) mid FROM cd_reservas WHERE id_empresa=%s "
                "      GROUP BY id_reserva) x ON r.id=x.mid "
                "WHERE r.estado IN ('SOFT_CREATED','HARD_CONFIRMED') AND r.ttl_expira IS NOT NULL "
                "  AND r.ttl_expira < %s", (emp, datetime.now()))
            ids = [(list(f.values())[0] if isinstance(f, dict) else f[0]) for f in cur.fetchall()]
        for rid in ids:
            if expirar(rid, actor="scheduler", id_empresa=emp):
                expiradas += 1
    except Exception as e:
        logger.error("barrer_expiradas: %s", e)
    return expiradas


def reservar_desde_plan(id_tx, plan, *, tipo="soft", id_linea=None, id_empresa=None, actor=None,
                        canal=None):
    """Crea las reservas de un Plan de Cumplimiento (una por asignación, incluidas parcialidades
    multi-origen). El Plan es efímero: NO se toca; solo se leen sus asignaciones. Devuelve los
    id_reserva creados. La invoca la ejecución (Workflow), no Fulfillment ni Availability."""
    creadas = []
    for asig in getattr(plan, "asignaciones", ()) or ():
        rid = reservar(id_tx, plan.codigo, asig.get("cantidad", 0), asig.get("bucket"),
                       tipo=tipo, id_linea=id_linea, id_empresa=id_empresa, actor=actor, canal=canal)
        if rid:
            creadas.append(rid)
    return creadas


def registrar_job():
    """Registra el barrido de caducidades en el Scheduler (capacidades, degradable/opt-in)."""
    try:
        from src.platform import capabilities as cap
        sch = cap.scheduler()
        if sch is not None and hasattr(sch, "registrar_job"):
            sch.registrar_job("cd_reservas_expiry", lambda *_a, **_k: barrer_expiradas())
            return True
    except Exception as e:
        logger.debug("registrar_job scheduler no disponible: %s", e)
    return False


def descriptor() -> dict:
    return {"servicio": "cd_reservas", "rfc": "CD-005", "fase": FASE, "estado": "implementado",
            "ledger": "append-only", "estados": list(ESTADOS), "activos": list(ACTIVOS),
            "unico_bloqueo_atp": True, "pertenece_a_transaccion": True, "omnicanal": True,
            "mueve_stock": False, "toca_kardex": False,
            "ttl_defecto_min": dict(_TTL_DEFECTO), "ttl_por": "rules(capabilities)"}


__all__ = ["FASE", "ESTADOS", "ACTIVOS", "reservar", "confirmar", "liberar", "consumir", "expirar",
           "estado", "reservado", "activas", "barrer_expiradas", "reservar_desde_plan",
           "registrar_job", "descriptor"]
