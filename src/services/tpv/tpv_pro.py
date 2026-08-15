"""
TPV PRO (Módulo 7, enriquecimiento). Añade SOLO lo ausente tras la auditoría:
  · Aparcar / recuperar tickets en curso (multiticket paralelo por caja).
  · Arqueo por denominación (recuento físico de billetes/monedas → total contado y diferencia
    frente al esperado, reutilizando `db.caja.arqueo`).
  · Análisis rápido del turno (reutiliza `services.tpv.cierre_z.resumen_dia`).

Las promos escalonadas (nxm/segunda_unidad) se resolvieron extendiendo el evaluador existente
`db/promociones.py` (sin nueva tabla). Fidelización, devoluciones y cierre Z ya existían y NO se tocan.
Multiempresa, auditado, sin duplicación.
"""

import json
import logging

logger = logging.getLogger("tpv.pro")

# Denominaciones EUR estándar (billetes y monedas). Reutilizable por la GUI del arqueo.
DENOMINACIONES_EUR = [
    (500, "billete"), (200, "billete"), (100, "billete"), (50, "billete"), (20, "billete"),
    (10, "billete"), (5, "billete"),
    (2, "moneda"), (1, "moneda"), (0.50, "moneda"), (0.20, "moneda"), (0.10, "moneda"),
    (0.05, "moneda"), (0.02, "moneda"), (0.01, "moneda"),
]


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.tpv.identidad_tpv import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _tid(valor):
    """Coacciona id_tienda a INT (migr 0196): None/'' = sin tienda (NULL, consulta null-safe con <=>);
    el resto (código 'ALMC' incluido) al entero canónico (código no numérico → 0)."""
    if valor is None or valor == "":
        return None
    from src.db.empresa import tienda_actual_id_int
    return tienda_actual_id_int(valor)


def _audit(accion, detalle, tabla="tpv_tickets_aparcados"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("tpv", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Aparcar / recuperar ticket ───────────────────────────────────────────────
def aparcar_ticket(lineas, *, total=0, referencia=None, cliente=None, id_tienda=None, caja=1,
                   usuario=None, id_empresa=None) -> int | None:
    """Aparca un ticket en curso para atender a otro cliente y recuperarlo después.
    `lineas` es la lista de líneas del ticket (se serializa en JSON, sin tocar stock)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO tpv_tickets_aparcados (id_empresa, id_tienda, caja, referencia, "
                        "cliente, lineas, total, usuario) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, _tid(id_tienda), int(caja or 1), referencia, cliente,
                         json.dumps(lineas, ensure_ascii=False, default=str), float(total or 0), usuario))
            tid = cur.lastrowid
            c.commit()
        _audit("TICKET_APARCADO", f"{tid}:ref{referencia} total{total}")
        return tid
    except Exception as e:
        logger.error("aparcar_ticket: %s", e)
        return None


def tickets_aparcados(id_empresa=None, *, id_tienda=None, caja=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = "SELECT * FROM tpv_tickets_aparcados WHERE id_empresa<=>%s AND estado='APARCADO'"
            p = [emp]
            if id_tienda is not None:
                q += " AND id_tienda<=>%s"; p.append(_tid(id_tienda))
            if caja is not None:
                q += " AND caja=%s"; p.append(int(caja))
            q += " ORDER BY creado DESC"
            cur.execute(q, p)
            filas = _filas(cur)
        for f in filas:
            try:
                f["lineas"] = json.loads(f.get("lineas") or "[]")
            except Exception:
                f["lineas"] = []
        return filas
    except Exception as e:
        logger.error("tickets_aparcados: %s", e)
        return []


def recuperar_ticket(id_ticket, id_empresa=None) -> dict | None:
    """Recupera un ticket aparcado (devuelve sus líneas) y lo marca como RECUPERADO."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM tpv_tickets_aparcados WHERE id=%s AND estado='APARCADO'", (id_ticket,))
            filas = _filas(cur)
            if not filas:
                return None
            cur.execute("UPDATE tpv_tickets_aparcados SET estado='RECUPERADO', recuperado=NOW() "
                        "WHERE id=%s", (id_ticket,))
            c.commit()
        t = filas[0]
        try:
            t["lineas"] = json.loads(t.get("lineas") or "[]")
        except Exception:
            t["lineas"] = []
        _audit("TICKET_RECUPERADO", f"{id_ticket}")
        return t
    except Exception as e:
        logger.error("recuperar_ticket: %s", e)
        return None


# ── Arqueo por denominación ──────────────────────────────────────────────────
def registrar_arqueo_denominaciones(id_sesion, conteo, *, usuario=None, id_empresa=None) -> dict:
    """Registra el recuento físico de efectivo por denominación y calcula la diferencia frente
    al esperado (reutiliza `db.caja.arqueo`).
    `conteo`: dict {valor_unidad: unidades} p.ej. {50: 3, 20: 5, 1: 10, 0.50: 4}."""
    emp = _emp(id_empresa)
    total = 0.0
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            # Reemplaza el conteo previo de la sesión (idempotente por recuento).
            cur.execute("DELETE FROM tpv_arqueo_denominaciones WHERE id_sesion=%s", (id_sesion,))
            tipos = {float(v): t for v, t in DENOMINACIONES_EUR}
            for valor, unidades in (conteo or {}).items():
                valor = float(valor); unidades = int(unidades or 0)
                subtotal = round(valor * unidades, 2)
                total += subtotal
                cur.execute("INSERT INTO tpv_arqueo_denominaciones (id_empresa, id_sesion, valor_unidad, "
                            "tipo, unidades, subtotal, usuario) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (emp, id_sesion, valor, tipos.get(valor, "moneda"), unidades, subtotal, usuario))
            c.commit()
        total = round(total, 2)
        esperado = 0.0
        try:
            from src.db import caja
            esperado = float(caja.arqueo(id_sesion, emp).get("esperado", 0) or 0)
        except Exception:
            pass
        dif = round(total - esperado, 2)
        _audit("ARQUEO_DENOMINACIONES", f"sesion{id_sesion} contado{total} dif{dif}",
               "tpv_arqueo_denominaciones")
        return {"ok": True, "contado": total, "esperado": esperado, "diferencia": dif,
                "cuadra": abs(dif) < 0.01}
    except Exception as e:
        logger.error("registrar_arqueo_denominaciones: %s", e)
        return {"ok": False, "motivo": str(e), "contado": round(total, 2)}


def detalle_arqueo(id_sesion, id_empresa=None) -> list:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT valor_unidad, tipo, unidades, subtotal FROM tpv_arqueo_denominaciones "
                        "WHERE id_sesion=%s ORDER BY valor_unidad DESC", (id_sesion,))
            return _filas(cur)
    except Exception as e:
        logger.error("detalle_arqueo: %s", e)
        return []


# ── Análisis del turno (reutiliza cierre_z.resumen_dia) ──────────────────────
def analisis_turno(fecha, *, caja=None, id_empresa=None) -> dict:
    """Análisis rápido de ventas del turno reutilizando el resumen ya calculado por el cierre Z."""
    try:
        from src.services.tpv import cierre_z
        return cierre_z.resumen_dia(fecha, _emp(id_empresa), caja=caja)
    except Exception as e:
        logger.error("analisis_turno: %s", e)
        return {}
