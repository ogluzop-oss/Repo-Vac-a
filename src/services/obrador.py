"""
Obrador / producción diaria (edición Bakery). Registra el parte de producción del día (productos elaborados +
cantidades). Al producir: da de alta stock VENDIBLE del terminado (`sumar_stock_recepcion` + kárdex
ENTRADA_PRODUCCION) y, si el producto tiene BOM, CONSUME los ingredientes por la salida de stock OFICIAL
(`salida_stock_oficial` → clamp + kárdex + FEFO). Reutiliza los motores de stock GENERALES (N7 — no crea un motor
paralelo); flujo simplificado, distinto de la OF completa del MRP. Multi-tenant.

La FUNCIÓN es exclusiva de la edición Bakery (`verticales.visible("bakery.obrador")`); el servicio es general.
"""

import datetime as _dt
import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("bakery.obrador")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _usuario(usuario=None):
    if usuario:
        return usuario
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        return str(u.get("nombre") or u.get("usuario") or "") or None
    except Exception:
        return None


def _coste_unitario(codigo, id_empresa) -> float:
    """Coste unitario de un ingrediente desde `articulos` (coste_medio → coste_actual → ultimo_coste →
    precio), filtrado por empresa (PK compuesta). 0.0 si no hay dato."""
    for col in ("coste_medio", "coste_actual", "ultimo_coste", "precio"):
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(f"SELECT {col} FROM articulos WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
                r = cur.fetchone()
                v = (r[0] if r and not isinstance(r, dict) else (r or {}).get(col)) if r else None
                if v is not None and float(v) > 0:
                    return float(v)
        except Exception:
            continue
    return 0.0


def producir(codigo, cantidad, *, id_empresa=None, usuario=None) -> dict:
    """Produce `cantidad` del terminado `codigo`: consume ingredientes de su BOM (si la tiene) por la salida
    oficial y da de alta el stock vendible del terminado (+ kárdex ENTRADA_PRODUCCION). Devuelve lo consumido."""
    emp = _emp(id_empresa)
    cantidad = int(cantidad or 0)
    if not emp or not codigo or cantidad <= 0:
        return {"ok": False, "error": "datos inválidos"}
    usr = _usuario(usuario)
    consumidos = []
    coste_mp = 0.0
    # 1. Consumo de ingredientes (si hay BOM) — salida de stock OFICIAL.
    try:
        from src.db.salida_stock import salida_stock_oficial
        from src.services.mrp import bom
        for comp in bom.explosionar(codigo, cantidad, id_empresa=emp):
            ccod = comp.get("componente") or comp.get("codigo")
            nec = int(comp.get("cantidad") or comp.get("necesario") or comp.get("cantidad_neta") or 0)
            if not ccod or nec <= 0:
                continue
            sal = salida_stock_oficial(ccod, nec, id_documento=f"OBR:{codigo}", id_empresa=emp,
                                       contexto="obrador", tipo="SALIDA_PRODUCCION", origen="OBRADOR", usuario=usr)
            faltante = int((sal or {}).get("faltante") or 0)
            servido = max(0, nec - faltante)                        # unidades realmente consumidas
            coste_mp += _coste_unitario(ccod, emp) * servido
            consumidos.append({"componente": ccod, "cantidad": nec, "faltante": faltante})
    except Exception as e:
        logger.debug("obrador consumo BOM (%s): %s", codigo, e)
    # 2. Alta del terminado: stock vendible + kárdex de producción.
    try:
        from src.db.conexion import sumar_stock_recepcion
        sumar_stock_recepcion(codigo, cantidad, id_empresa=emp)
    except Exception as e:
        logger.error("obrador alta terminado (%s): %s", codigo, e)
        return {"ok": False, "error": str(e), "consumidos": consumidos}
    try:
        from src.db import kardex
        kardex.registrar_movimiento(codigo, "ENTRADA_PRODUCCION", cantidad, id_documento=f"OBR:{codigo}",
                                    origen="OBRADOR", usuario=usr, id_empresa=emp,
                                    observaciones="Producción de obrador")
    except Exception:
        pass
    # 3. Contabilidad: el coste de la materia prima consumida se lleva AUTOMÁTICAMENTE a "gastos materia prima"
    #    (Debe 601 / Haber 300). Best-effort: nunca rompe la producción; no hace nada si contabilidad no está activa.
    if coste_mp > 0:
        try:
            from src.services.contabilidad import posting as _P
            ref = f"{codigo}:{_dt.datetime.now():%Y%m%d%H%M%S%f}"
            _P.registrar_consumo_materia_prima(ref, coste_mp, id_empresa=emp,
                                               concepto=f"Consumo obrador · {codigo}")
        except Exception as e:
            logger.debug("obrador contab consumo (%s): %s", codigo, e)
    return {"ok": True, "codigo": codigo, "producido": cantidad, "consumidos": consumidos,
            "coste_materia_prima": round(coste_mp, 2)}


def registrar_produccion_diaria(items, *, fecha=None, turno=None, responsable=None, id_empresa=None,
                                usuario=None) -> dict:
    """Registra el parte del día y produce cada línea. `items` = [{'codigo','cantidad'}]. Devuelve
    {parte, lineas, producidos}."""
    emp = _emp(id_empresa)
    if not emp:
        return {"ok": False, "error": "sin empresa"}
    validas = []
    for it in items or []:
        cod = str(it.get("codigo") or "").strip()
        cant = int(it.get("cantidad") or 0)
        if cod and cant > 0:
            validas.append((cod, cant))
    if not validas:
        return {"ok": False, "error": "no hay líneas válidas"}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO obrador_partes (id_empresa, fecha, turno, responsable, usuario) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (emp, fecha or _dt.date.today(), turno, responsable, _usuario(usuario)))
            pid = cur.lastrowid
            cur.executemany("INSERT INTO obrador_partes_lineas (id_parte, codigo_articulo, cantidad) "
                            "VALUES (%s,%s,%s)", [(pid, c, q) for c, q in validas])
            conn.commit()
    except Exception as e:
        logger.error("registrar_produccion_diaria: %s", e)
        return {"ok": False, "error": str(e)}
    producidos = 0
    for cod, cant in validas:
        r = producir(cod, cant, id_empresa=emp, usuario=usuario)
        if r.get("ok"):
            producidos += cant
    _audit(emp, "OBRADOR_PARTE", f"parte={pid} lineas={len(validas)} producidos={producidos}")
    return {"ok": True, "parte": pid, "lineas": len(validas), "producidos": producidos}


def listar_partes(*, fecha=None, id_empresa=None, limite=100) -> list:
    emp = _emp(id_empresa)
    if not emp:
        return []
    q = "SELECT * FROM obrador_partes WHERE id_empresa=%s"
    p = [emp]
    if fecha:
        q += " AND fecha=%s"
        p.append(fecha)
    q += " ORDER BY id DESC LIMIT %s"
    p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, tuple(p))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_partes: %s", e)
        return []


def obtener_parte(id_parte, *, id_empresa=None) -> dict | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _fila_a_dict
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM obrador_partes WHERE id=%s AND id_empresa=%s", (id_parte, emp))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute("SELECT * FROM obrador_partes_lineas WHERE id_parte=%s ORDER BY id", (id_parte,))
            cab["lineas"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.debug("obtener_parte: %s", e)
        return None


def _audit(id_empresa, accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("bakery", accion, "obrador_partes", f"{id_empresa}: {detalle}")
    except Exception:
        pass
