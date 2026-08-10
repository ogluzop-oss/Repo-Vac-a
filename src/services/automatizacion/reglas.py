"""
Motor de reglas empresariales (Paquete Enterprise 4, SUBFASE 4.2). Reglas SI (condicion)
ENTONCES (accion), configurables, priorizadas, activables y versionables (tabla
automatizaciones_reglas). Las CONDICIONES se apoyan en IA/Prediccion/adaptadores existentes.
"""

import logging

from src.services.ia import adaptadores as IAA

logger = logging.getLogger("automatizacion.reglas")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


# ── Condiciones (predicados reutilizando IA/Prediccion) ───────────────────────
def _stock_critico(emp):
    b = IAA.articulos_bajo_umbral(emp)
    return (len(b) > 0, {"items": b, "n": len(b), "prioridad": "ALTA",
                         "mensaje": f"{len(b)} articulos por debajo del umbral"})


def _prediccion_rotura(emp):
    try:
        from src.services import prediccion
        s = prediccion.servicio().stock(emp)
        n = next((p["valor"] for p in s.get("predicciones", []) if p["metrica"] == "rotura_stock"), 0)
        return (n > 0, {"items": IAA.articulos_bajo_umbral(emp), "n": n, "prioridad": "ALTA",
                        "mensaje": f"Prevision de rotura en {n} articulos"})
    except Exception:
        return (False, {})


def _impago_30d(emp):
    fp = IAA.facturas_pendientes(emp)
    return (len(fp) >= 5, {"items": fp, "n": len(fp), "prioridad": "ALTA",
                           "mensaje": f"{len(fp)} facturas impagadas"})


def _sin_ventas_120d(emp):
    from src.services.prediccion import adaptadores as PA
    sm = PA.sin_movimiento(emp, dias=120)
    return (len(sm) > 0, {"items": sm, "n": len(sm), "prioridad": "BAJA",
                          "mensaje": f"{len(sm)} productos sin ventas en 120 dias"})


def _contrato_caduca_30d(emp):
    cv = IAA.contratos_por_vencer(emp, dias=30)
    return (len(cv) > 0, {"items": cv, "n": len(cv), "prioridad": "MEDIA",
                          "mensaje": f"{len(cv)} contratos vencen en 30 dias"})


def _riesgo_impago_alto(emp):
    try:
        from src.services import prediccion
        t = prediccion.servicio().tesoreria(emp)
        alto = any(str(p.get("valor")) == "alto" for p in t.get("predicciones", []))
        return (alto, {"prioridad": "ALTA", "mensaje": "Riesgo alto de impago"})
    except Exception:
        return (False, {})


def _siempre(emp):
    return (True, {})


CONDICIONES = {
    "stock_critico": _stock_critico, "prediccion_rotura": _prediccion_rotura,
    "impago_30d": _impago_30d, "sin_ventas_120d": _sin_ventas_120d,
    "contrato_caduca_30d": _contrato_caduca_30d, "riesgo_impago_alto": _riesgo_impago_alto,
    "siempre": _siempre,
}


# ── Catalogo semilla de reglas (SUBFASE 4.2) ──────────────────────────────────
CATALOGO = [
    {"codigo": "R_STOCK_CRITICO", "nombre": "Stock critico → propuesta de compra",
     "trigger_tipo": "programado", "trigger_valor": "diario", "condicion": "stock_critico",
     "accion": "crear_propuesta_compra", "params": None, "nivel": "proponer", "prioridad": "ALTA"},
    {"codigo": "R_IMPAGO_30D", "nombre": "Facturas impagadas → tarea administracion",
     "trigger_tipo": "programado", "trigger_valor": "diario", "condicion": "impago_30d",
     "accion": "crear_tarea", "params": '{"modulo":"tesoreria","titulo":"Revisar facturas impagadas"}',
     "nivel": "proponer", "prioridad": "ALTA"},
    {"codigo": "R_SIN_VENTAS_120", "nombre": "Producto sin ventas 120d → proponer liquidacion",
     "trigger_tipo": "programado", "trigger_valor": "semanal", "condicion": "sin_ventas_120d",
     "accion": "proponer_liquidacion", "params": None, "nivel": "informar", "prioridad": "BAJA"},
    {"codigo": "R_CONTRATO_30D", "nombre": "Contrato caduca 30d → tarea RRHH",
     "trigger_tipo": "programado", "trigger_valor": "diario", "condicion": "contrato_caduca_30d",
     "accion": "crear_tarea", "params": '{"modulo":"rrhh","titulo":"Contratos por vencer"}',
     "nivel": "proponer", "prioridad": "MEDIA"},
    {"codigo": "R_PRED_ROTURA", "nombre": "Prediccion de rotura → propuesta de compra",
     "trigger_tipo": "prediccion", "trigger_valor": "rotura", "condicion": "prediccion_rotura",
     "accion": "crear_propuesta_compra", "params": None, "nivel": "proponer", "prioridad": "ALTA"},
    {"codigo": "R_RIESGO_IMPAGO", "nombre": "Riesgo alto de impago → tarea administracion",
     "trigger_tipo": "prediccion", "trigger_valor": "impago", "condicion": "riesgo_impago_alto",
     "accion": "crear_tarea", "params": '{"modulo":"tesoreria","titulo":"Riesgo de impago detectado"}',
     "nivel": "proponer", "prioridad": "ALTA"},
    {"codigo": "R_PRECIO_EVENTO", "nombre": "Precio actualizado → notificar",
     "trigger_tipo": "evento", "trigger_valor": "PRECIO_ACTUALIZADO", "condicion": "siempre",
     "accion": "notificar", "params": '{"modulo":"catalogo","titulo":"Precio actualizado (automatizacion)"}',
     "nivel": "informar", "prioridad": "BAJA"},
]


def sembrar(cur) -> int:
    """Inserta el catalogo semilla (global, id_empresa NULL) si no existe. Idempotente."""
    n = 0
    for r in CATALOGO:
        cur.execute("SELECT 1 FROM automatizaciones_reglas WHERE id_empresa IS NULL AND codigo=%s",
                    (r["codigo"],))
        if cur.fetchone():
            continue
        cur.execute("INSERT INTO automatizaciones_reglas (id_empresa, codigo, nombre, trigger_tipo, "
                    "trigger_valor, condicion, accion, params, nivel, prioridad, activa) "
                    "VALUES (NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)",
                    (r["codigo"], r["nombre"], r["trigger_tipo"], r["trigger_valor"], r["condicion"],
                     r["accion"], r.get("params"), r["nivel"], r["prioridad"]))
        n += 1
    return n


def _dicts(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def listar_activas(id_empresa=None, *, trigger_tipo=None, trigger_valor=None) -> list:
    """Reglas activas (globales + de la empresa). Si la BD no esta sembrada, usa el catalogo."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        q = ("SELECT * FROM automatizaciones_reglas WHERE activa=1 "
             "AND (id_empresa IS NULL OR id_empresa=%s)")
        p = [emp]
        if trigger_tipo:
            q += " AND trigger_tipo=%s"; p.append(trigger_tipo)
        if trigger_valor:
            q += " AND trigger_valor=%s"; p.append(trigger_valor)
        q += " ORDER BY FIELD(prioridad,'CRITICA','ALTA','MEDIA','BAJA','INFORMATIVA'), codigo"
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(q, p)
            filas = _dicts(cur)
        if filas:
            return filas
    except Exception as e:
        logger.debug("listar_activas: %s", e)
    # Fallback: catalogo en memoria.
    out = list(CATALOGO)
    if trigger_tipo:
        out = [r for r in out if r["trigger_tipo"] == trigger_tipo]
    if trigger_valor:
        out = [r for r in out if r.get("trigger_valor") == trigger_valor]
    return out


def evaluar(regla, id_empresa=None):
    """(disparada, contexto) evaluando la condicion de la regla."""
    fn = CONDICIONES.get(regla.get("condicion"))
    if not fn:
        return (False, {})
    try:
        return fn(_emp(id_empresa))
    except Exception as e:
        logger.debug("evaluar %s: %s", regla.get("codigo"), e)
        return (False, {})


def configurar(codigo, id_empresa=None, *, activa=None, nivel=None) -> bool:
    """Activa/desactiva o cambia el nivel de una regla PARA una empresa (crea override + version)."""
    emp = _emp(id_empresa)
    base = next((r for r in CATALOGO if r["codigo"] == codigo), None)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT nombre, trigger_tipo, trigger_valor, condicion, accion, params, "
                        "nivel, prioridad FROM automatizaciones_reglas WHERE codigo=%s "
                        "AND (id_empresa=%s OR id_empresa IS NULL) ORDER BY id_empresa IS NULL LIMIT 1",
                        (codigo, emp))
            r = cur.fetchone()
            src = (r if isinstance(r, dict) else None) or base or {}
            g = lambda i, k, d=None: (r[i] if (r and not isinstance(r, dict)) else src.get(k, d))
            cur.execute(
                "INSERT INTO automatizaciones_reglas (id_empresa, codigo, nombre, trigger_tipo, "
                "trigger_valor, condicion, accion, params, nivel, prioridad, activa, version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1) ON DUPLICATE KEY UPDATE "
                "nivel=VALUES(nivel), activa=VALUES(activa), version=version+1",
                (emp, codigo, g(0, "nombre"), g(1, "trigger_tipo", "programado"),
                 g(2, "trigger_valor"), g(3, "condicion", "siempre"), g(4, "accion", "notificar"),
                 g(5, "params"), (nivel or g(6, "nivel", "proponer")), g(7, "prioridad", "MEDIA"),
                 (1 if activa is None else (1 if activa else 0))))
            c.commit()
        return True
    except Exception as e:
        logger.error("configurar regla %s: %s", codigo, e)
        return False
