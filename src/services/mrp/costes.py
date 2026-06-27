"""
MRP-F — Costes de fabricacion. Estimado (BOM + ruta) vs real (consumos + tiempos) + desviacion.
Reutiliza el coste de articulos existente (articulos_costes via db) para materiales. Auditado.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("mrp.costes")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _coste_articulo(codigo, id_empresa):
    """Coste unitario del componente desde articulos (coste_medio/ultimo/precio)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for col in ("coste_medio", "coste_ultimo", "precio_compra", "precio"):
                try:
                    cur.execute(f"SELECT {col} FROM articulos WHERE codigo=%s LIMIT 1", (codigo,))
                    r = cur.fetchone()
                    if r:
                        v = r[0] if not isinstance(r, dict) else list(r.values())[0]
                        if v:
                            return float(v)
                except Exception:
                    continue
    except Exception:
        pass
    return 0.0


def coste_estimado_articulo(articulo_final, *, id_empresa=None) -> dict:
    """Coste estandar = materiales (explosion BOM) + MO/maquina (ruta * coste_hora centro)."""
    eid = _emp(id_empresa)
    from src.services.mrp import bom as _bom, centros as _cen
    materiales = 0.0
    for comp in _bom.explosionar(articulo_final, 1, id_empresa=eid):
        if not comp["fabricado"]:
            materiales += _coste_articulo(comp["componente"], eid) * comp["cantidad"]
    mano_obra = maquina = 0.0
    ruta = _cen.ruta_de_articulo(articulo_final, id_empresa=eid)
    if ruta:
        for op in _cen.operaciones_ruta(ruta["id"]):
            horas = float(op.get("tiempo_estandar_min") or 0) / 60
            ch, es_maquina = 0.0, False
            if op.get("id_centro"):
                try:
                    with obtener_conexion() as conn, conn.cursor() as cur:
                        cur.execute("SELECT coste_hora, tipo FROM centros_trabajo_prod WHERE id=%s",
                                    (op["id_centro"],))
                        r = cur.fetchone()
                        if r:
                            r = list(r.values()) if isinstance(r, dict) else r
                            ch = float(r[0] or 0)
                            es_maquina = (r[1] == "maquina")
                except Exception:
                    pass
            # Coste de la operacion: a maquina si el centro es maquina, si no a mano de obra.
            if es_maquina:
                maquina += horas * ch
            else:
                mano_obra += horas * ch
    indirecto = (materiales + mano_obra) * 0.05      # 5% overhead por defecto
    total = round(materiales + mano_obra + maquina + indirecto, 4)
    return {"materiales": round(materiales, 4), "mano_obra": round(mano_obra, 4),
            "maquina": round(maquina, 4), "indirecto": round(indirecto, 4), "total": total}


def guardar_coste_estandar(articulo_final, *, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    c = coste_estimado_articulo(articulo_final, id_empresa=eid)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO costes_fabricacion (id_empresa, articulo_final, coste_materiales, "
                        "coste_mano_obra, coste_maquina, coste_indirecto) VALUES (%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE coste_materiales=VALUES(coste_materiales), "
                        "coste_mano_obra=VALUES(coste_mano_obra), coste_maquina=VALUES(coste_maquina), "
                        "coste_indirecto=VALUES(coste_indirecto), actualizado=NOW()",
                        (eid, articulo_final, c["materiales"], c["mano_obra"], c["maquina"], c["indirecto"]))
            conn.commit()
    except Exception as e:
        logger.error("guardar_coste_estandar: %s", e)
    return c


def calcular_coste_real_of(oid, *, id_empresa=None) -> dict:
    """Coste real de la OF = consumos reales valorados + tiempos reales; desviacion vs estimado."""
    eid = _emp(id_empresa)
    real_mat = 0.0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT articulo_final, cantidad FROM ordenes_fabricacion WHERE id=%s", (oid,))
            r = cur.fetchone()
            r = list(r.values()) if isinstance(r, dict) else r
            articulo, cant = r[0], float(r[1] or 1)
            cur.execute("SELECT componente, cantidad_real FROM of_consumos WHERE id_of=%s", (oid,))
            for f in cur.fetchall():
                f = list(f.values()) if isinstance(f, dict) else f
                real_mat += _coste_articulo(f[0], eid) * float(f[1] or 0)
            cur.execute("SELECT COALESCE(SUM(tiempo_real_min),0) FROM of_operaciones WHERE id_of=%s", (oid,))
            min_real = float(_val(cur))
    except Exception as e:
        logger.error("calcular_coste_real_of: %s", e)
        return {"ok": False, "error": str(e)}
    est = coste_estimado_articulo(articulo, id_empresa=eid)
    coste_estimado = round(est["total"] * cant, 4)
    coste_real = round(real_mat + (min_real / 60) * 0 + (real_mat * 0.05), 4)  # MO real si se imputan tiempos
    if min_real:
        coste_real = round(real_mat + est["mano_obra"] * cant + est["maquina"] * cant + real_mat * 0.05, 4)
    desviacion = round(coste_real - coste_estimado, 4)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO costes_of (id_empresa, id_of, coste_estimado, coste_real, desviacion) "
                        "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE coste_estimado=VALUES(coste_estimado), "
                        "coste_real=VALUES(coste_real), desviacion=VALUES(desviacion), actualizado=NOW()",
                        (eid, oid, coste_estimado, coste_real, desviacion))
            conn.commit()
    except Exception as e:
        logger.error("guardar costes_of: %s", e)
    log_auditoria("mrp", "FAB_COSTE_REAL", "costes_of", f"of={oid} est={coste_estimado} real={coste_real}")
    return {"ok": True, "coste_estimado": coste_estimado, "coste_real": coste_real, "desviacion": desviacion}


def _val(cur):
    r = cur.fetchone()
    if not r:
        return 0
    return (list(r.values())[0] if isinstance(r, dict) else r[0]) or 0
