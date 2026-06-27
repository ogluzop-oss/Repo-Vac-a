"""
FASE A — Presupuestos financieros. Versiones + escenarios (base/optimista/pesimista/personalizado)
+ lineas por categoria (ingreso/gasto/inversion/financiacion/impuesto) y periodo. Comparativa
Real vs Presupuesto (real desde contabilidad PyG por periodo) con desviacion €/% y forecast de cierre.
Multiempresa, auditado. NO duplica contabilidad: la lee.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("finanzas.presupuestos")
PERIODICIDADES = {"anual": 1, "trimestral": 4, "mensual": 12}
ESCENARIOS = ("base", "optimista", "pesimista", "personalizado")
CATEGORIAS = ("ingreso", "gasto", "inversion", "financiacion", "impuesto")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_presupuesto(codigo, nombre, ejercicio, *, periodicidad="mensual", id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO presupuestos_financieros (id_empresa, codigo, nombre, ejercicio, periodicidad) "
                        "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                        "periodicidad=VALUES(periodicidad)", (eid, codigo, nombre, ejercicio, periodicidad))
            cur.execute("SELECT id FROM presupuestos_financieros WHERE id_empresa=%s AND codigo=%s AND ejercicio=%s",
                        (eid, codigo, ejercicio))
            pid = cur.fetchone()
            pid = pid[0] if not isinstance(pid, dict) else list(pid.values())[0]
            cur.execute("INSERT IGNORE INTO presupuesto_versiones (id_empresa, id_presupuesto, version) "
                        "VALUES (%s,%s,1)", (eid, pid))
            for esc in ("base", "optimista", "pesimista"):
                factor = {"base": 1.0, "optimista": 1.1, "pesimista": 0.9}[esc]
                cur.execute("INSERT IGNORE INTO presupuesto_escenarios (id_empresa, id_presupuesto, tipo, factor) "
                            "VALUES (%s,%s,%s,%s)", (eid, pid, esc, factor))
            conn.commit()
        log_auditoria("finanzas", "FIN_PPTO_CREADO", "presupuestos_financieros", f"ppto={pid} {codigo}")
        return pid
    except Exception as e:
        logger.error("crear_presupuesto: %s", e)
        return None


def añadir_linea(id_presupuesto, categoria, concepto, periodo, importe, *, version=1,
                 escenario="base", cuenta_contable=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    if categoria not in CATEGORIAS:
        raise ValueError(f"categoria invalida: {categoria}")
    if escenario not in ESCENARIOS:
        raise ValueError(f"escenario invalido: {escenario}")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO presupuesto_lineas (id_empresa, id_presupuesto, version, escenario, "
                        "categoria, concepto, cuenta_contable, periodo, importe) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, id_presupuesto, version, escenario, categoria, concepto, cuenta_contable,
                         periodo, importe))
            lid = cur.lastrowid
            conn.commit()
        return lid
    except ValueError:
        raise
    except Exception as e:
        logger.error("añadir_linea: %s", e)
        return None


def nueva_version(id_presupuesto, *, nota=None, copiar_de=None, id_empresa=None) -> int:
    """Crea una nueva version (opcionalmente copiando las lineas de otra). Devuelve el nº de version."""
    eid = _emp(id_empresa)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(version),0)+1 FROM presupuesto_versiones WHERE id_presupuesto=%s",
                    (id_presupuesto,))
        ver = cur.fetchone()
        ver = ver[0] if not isinstance(ver, dict) else list(ver.values())[0]
        cur.execute("INSERT INTO presupuesto_versiones (id_empresa, id_presupuesto, version, nota) "
                    "VALUES (%s,%s,%s,%s)", (eid, id_presupuesto, ver, nota))
        if copiar_de:
            cur.execute("INSERT INTO presupuesto_lineas (id_empresa, id_presupuesto, version, escenario, "
                        "categoria, concepto, cuenta_contable, periodo, importe) "
                        "SELECT id_empresa, id_presupuesto, %s, escenario, categoria, concepto, "
                        "cuenta_contable, periodo, importe FROM presupuesto_lineas WHERE id_presupuesto=%s "
                        "AND version=%s", (ver, id_presupuesto, copiar_de))
        cur.execute("UPDATE presupuestos_financieros SET version_activa=%s WHERE id=%s", (ver, id_presupuesto))
        conn.commit()
    log_auditoria("finanzas", "FIN_PPTO_VERSION", "presupuesto_versiones", f"ppto={id_presupuesto} v{ver}")
    return ver


def presupuestado(id_presupuesto, *, version=None, escenario="base", id_empresa=None) -> dict:
    """Totales presupuestados por categoria (aplicando el factor del escenario)."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if version is None:
                cur.execute("SELECT version_activa FROM presupuestos_financieros WHERE id=%s", (id_presupuesto,))
                rv = cur.fetchone()
                version = (rv[0] if not isinstance(rv, dict) else list(rv.values())[0]) if rv else 1
            cur.execute("SELECT factor FROM presupuesto_escenarios WHERE id_presupuesto=%s AND tipo=%s",
                        (id_presupuesto, escenario))
            rf = cur.fetchone()
            factor = float((rf[0] if not isinstance(rf, dict) else list(rf.values())[0]) if rf else 1.0)
            # Si el escenario tiene lineas propias usalas; si no, usa 'base' * factor.
            cur.execute("SELECT categoria, SUM(importe) FROM presupuesto_lineas WHERE id_presupuesto=%s "
                        "AND version=%s AND escenario=%s GROUP BY categoria", (id_presupuesto, version, escenario))
            filas = cur.fetchall()
            usar_factor = False
            if not filas and escenario != "base":
                cur.execute("SELECT categoria, SUM(importe) FROM presupuesto_lineas WHERE id_presupuesto=%s "
                            "AND version=%s AND escenario='base' GROUP BY categoria", (id_presupuesto, version))
                filas = cur.fetchall(); usar_factor = True
        out = {c: 0.0 for c in CATEGORIAS}
        for r in filas:
            r = list(r.values()) if isinstance(r, dict) else r
            out[r[0]] = round(float(r[1] or 0) * (factor if usar_factor else 1), 2)
        out["resultado"] = round(out["ingreso"] - out["gasto"] - out["impuesto"], 2)
        return out
    except Exception as e:
        logger.error("presupuestado: %s", e)
        return {}


def real_vs_presupuesto(id_presupuesto, *, escenario="base", id_empresa=None) -> dict:
    """Compara lo presupuestado con lo REAL (contabilidad PyG del ejercicio). Desviacion €/%."""
    eid = _emp(id_empresa)
    ppto = presupuestado(id_presupuesto, escenario=escenario, id_empresa=eid)
    real = {"ingreso": 0.0, "gasto": 0.0, "resultado": 0.0}
    ejercicio = None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT ejercicio FROM presupuestos_financieros WHERE id=%s", (id_presupuesto,))
            r = cur.fetchone()
            ejercicio = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
        from src.services.contabilidad import informes
        pyg = informes.perdidas_ganancias(id_empresa=eid, anio=ejercicio)
        real = {"ingreso": float(pyg.get("ingresos", 0)), "gasto": float(pyg.get("gastos", 0)),
                "resultado": float(pyg.get("resultado", 0))}
    except Exception as e:
        logger.debug("real_vs_presupuesto/contab: %s", e)

    def _desv(real_v, ppto_v):
        dif = round(real_v - ppto_v, 2)
        pct = round(dif * 100 / ppto_v, 2) if ppto_v else None
        return {"real": round(real_v, 2), "presupuesto": round(ppto_v, 2), "desviacion": dif, "desviacion_pct": pct}

    return {
        "ejercicio": ejercicio, "escenario": escenario,
        "ingreso": _desv(real["ingreso"], ppto.get("ingreso", 0)),
        "gasto": _desv(real["gasto"], ppto.get("gasto", 0)),
        "resultado": _desv(real["resultado"], ppto.get("resultado", 0)),
    }


def forecast_cierre(id_presupuesto, *, periodos_transcurridos, escenario="base", id_empresa=None) -> dict:
    """Forecast de cierre = real proporcionado al periodo + presupuesto del resto (lineal)."""
    eid = _emp(id_empresa)
    total_periodos = 12
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT periodicidad FROM presupuestos_financieros WHERE id=%s", (id_presupuesto,))
            r = cur.fetchone()
            per = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else "mensual"
            total_periodos = PERIODICIDADES.get(per, 12)
    except Exception:
        pass
    cmp = real_vs_presupuesto(id_presupuesto, escenario=escenario, id_empresa=eid)
    restantes = max(0, total_periodos - periodos_transcurridos)
    out = {}
    for cat in ("ingreso", "gasto", "resultado"):
        real = cmp[cat]["real"]
        ppto = cmp[cat]["presupuesto"]
        ppto_restante = ppto * restantes / total_periodos if total_periodos else 0
        out[cat] = round(real + ppto_restante, 2)
    log_auditoria("finanzas", "FIN_PPTO_FORECAST", "presupuestos_financieros", f"ppto={id_presupuesto}")
    return out


def listar(*, ejercicio=None, id_empresa=None) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM presupuestos_financieros WHERE id_empresa=%s"
    p = [eid]
    if ejercicio:
        q += " AND ejercicio=%s"; p.append(ejercicio)
    q += " ORDER BY ejercicio DESC, codigo"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar ppto: %s", e)
        return []
