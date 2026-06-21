"""
Motor de promociones (VTA.2).

Promociones por artículo/categoría/familia/cliente/segmento/tienda con ventana temporal
(fecha/hora). Tipos: descuento_pct, importe_fijo, 2x1, pack, regalo. El evaluador devuelve
el mejor descuento aplicable a una línea SIN tocar el cálculo de venta existente (se invoca
como ayuda best-effort desde el TPV). Multiempresa. Sin Qt.
"""

import datetime as _dt
import logging

from src.db.conexion import (_filas_a_dicts, ensure_schema, obtener_conexion, transaccion)

logger = logging.getLogger("ventas.promociones")

TIPOS = ("descuento_pct", "importe_fijo", "2x1", "pack", "regalo")
AMBITOS = ("articulo", "categoria", "familia", "cliente", "segmento", "tienda")


def _emp(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return id_empresa or EMPRESA_DEFAULT_ID


def crear_promocion(nombre, tipo="descuento_pct", valor=0, ambito="articulo", id_tienda=None,
                    segmento=None, fecha_inicio=None, fecha_fin=None, hora_inicio=None,
                    hora_fin=None, prioridad=0, reglas=None, id_empresa=None) -> int | None:
    """Crea una promoción y sus reglas. `reglas`: [{clave, valor}] (p.ej. codigo/categoria/cliente)."""
    id_empresa = _emp(id_empresa)
    if tipo not in TIPOS:
        return None
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO promociones (id_empresa, nombre, tipo, valor, ambito, id_tienda, "
                        "segmento, fecha_inicio, fecha_fin, hora_inicio, hora_fin, prioridad) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, nombre, tipo, valor, ambito, id_tienda, segmento,
                         fecha_inicio, fecha_fin, hora_inicio, hora_fin, int(prioridad)))
            pid = cur.lastrowid
            for r in (reglas or []):
                cur.execute("INSERT INTO promociones_reglas (id_promocion, id_empresa, clave, valor) "
                            "VALUES (%s,%s,%s,%s)", (pid, id_empresa, r.get("clave"), str(r.get("valor"))))
            return pid
    except Exception as e:
        logger.error("crear_promocion: %s", e)
        return None


def listar_promociones(id_empresa=None, solo_activas=True) -> list:
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        cond = ["id_empresa=%s"]; params = [id_empresa]
        if solo_activas:
            cond.append("activa=1")
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM promociones WHERE {' AND '.join(cond)} "
                        "ORDER BY prioridad DESC, id_promocion", params)
            promos = _filas_a_dicts(cur, cur.fetchall())
            for p in promos:
                cur.execute("SELECT clave, valor FROM promociones_reglas WHERE id_promocion=%s",
                            (p["id_promocion"],))
                p["reglas"] = _filas_a_dicts(cur, cur.fetchall())
            return promos
    except Exception as e:
        logger.error("listar_promociones: %s", e)
        return []


def _vigente(p, ahora):
    if p.get("fecha_inicio") and ahora.date() < p["fecha_inicio"]:
        return False
    if p.get("fecha_fin") and ahora.date() > p["fecha_fin"]:
        return False
    # hora_inicio/fin pueden venir como timedelta (MySQL TIME)
    def _h(v):
        if v is None:
            return None
        if isinstance(v, _dt.timedelta):
            return (_dt.datetime.min + v).time()
        return v
    hi, hf = _h(p.get("hora_inicio")), _h(p.get("hora_fin"))
    if hi and ahora.time() < hi:
        return False
    if hf and ahora.time() > hf:
        return False
    return True


def _aplica(p, codigo, categoria, cliente_id, segmento, id_tienda):
    if p.get("id_tienda") and id_tienda and p["id_tienda"] != id_tienda:
        return False
    if p.get("segmento") and p["segmento"] != segmento:
        return False
    reglas = p.get("reglas") or []
    if not reglas:
        return True   # promoción global
    ctx = {"codigo": str(codigo), "categoria": str(categoria or ""),
           "cliente": str(cliente_id or ""), "segmento": str(segmento or "")}
    # Todas las reglas presentes deben casar (AND por clave; valores múltiples = OR).
    por_clave = {}
    for r in reglas:
        por_clave.setdefault(r["clave"], set()).add(str(r["valor"]))
    for clave, valores in por_clave.items():
        if ctx.get(clave) not in valores:
            return False
    return True


def evaluar_articulo(codigo, precio, cantidad=1, categoria=None, cliente_id=None,
                     segmento=None, id_tienda=None, id_empresa=None, ahora=None) -> dict:
    """Devuelve el MEJOR descuento aplicable a una línea: {promo, tipo, descuento, precio_final}.
    descuento es el importe total descontado de la línea (precio*cantidad). Best-effort."""
    id_empresa = _emp(id_empresa)
    ahora = ahora or _dt.datetime.now()
    base = round(float(precio) * int(cantidad), 2)
    mejor = {"promo": None, "tipo": None, "descuento": 0.0, "precio_final": base}
    try:
        for p in listar_promociones(id_empresa, solo_activas=True):
            if not _vigente(p, ahora) or not _aplica(p, codigo, categoria, cliente_id, segmento, id_tienda):
                continue
            tipo, val = p["tipo"], float(p["valor"] or 0)
            desc = 0.0
            if tipo == "descuento_pct":
                desc = round(base * val / 100.0, 2)
            elif tipo == "importe_fijo":
                desc = round(min(base, val * int(cantidad)), 2)
            elif tipo == "2x1":
                desc = round((int(cantidad) // 2) * float(precio), 2)
            elif tipo == "pack":
                desc = round(base * val / 100.0, 2)
            elif tipo == "regalo":
                desc = 0.0
            if desc > mejor["descuento"]:
                mejor = {"promo": p["id_promocion"], "tipo": tipo, "descuento": desc,
                         "precio_final": round(base - desc, 2)}
        return mejor
    except Exception as e:
        logger.error("evaluar_articulo(%s): %s", codigo, e)
        return mejor
