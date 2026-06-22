"""
Motor de conciliación bancaria (rama Tesorería, FASE 8).

Importa extractos (CSV/N43/CAMT.053) y empareja sus líneas con los movimientos de tesorería
por importe + fecha (tolerancia configurable) + referencia. Modos:
  • manual         → conciliar(linea, movimiento) explícito.
  • semiautomático → sugerir(linea) devuelve candidatos ordenados.
  • automático     → conciliar_automatico(extracto) empareja los casos no ambiguos.
Las líneas sin match quedan como diferencias.
"""

import datetime as _dt
import logging

from src.db import conciliacion_bancaria as _CB
from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.tesoreria import extractos as _EX

logger = logging.getLogger("conciliacion_svc")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def importar_extracto(contenido, formato, *, id_cuenta=None, nombre_fichero=None,
                      id_empresa=None) -> dict:
    """Parsea y persiste un extracto. Devuelve {id_extracto, num_lineas, formato}."""
    id_empresa = _emp(id_empresa)
    lineas = _EX.parsear(contenido, formato)
    fechas = [x["fecha"] for x in lineas if x.get("fecha")]
    eid = _CB.crear_extracto(id_cuenta, formato, nombre_fichero=nombre_fichero,
                             fecha_inicio=min(fechas) if fechas else None,
                             fecha_fin=max(fechas) if fechas else None,
                             num_lineas=len(lineas), id_empresa=id_empresa)
    for ln in lineas:
        _CB.anadir_linea(eid, ln["fecha"], ln["importe"], concepto=ln.get("concepto"),
                         referencia=ln.get("referencia"), saldo=ln.get("saldo"),
                         id_empresa=id_empresa)
    _CB.actualizar_num_lineas(eid, id_empresa)
    _audit("importa_extracto", f"extracto={eid} {formato} lineas={len(lineas)}")
    return {"id_extracto": eid, "num_lineas": len(lineas), "formato": (formato or "CSV").upper()}


def _candidatos(linea, tolerancia_dias, usados, id_cuenta, id_empresa):
    """Movimientos de tesorería que casan por importe exacto y fecha ±tolerancia."""
    f = linea["fecha"]
    if hasattr(f, "strftime"):
        f = f.strftime("%Y-%m-%d")
    base = _dt.datetime.strptime(str(f)[:10], "%Y-%m-%d").date()
    desde = (base - _dt.timedelta(days=tolerancia_dias)).strftime("%Y-%m-%d")
    hasta = (base + _dt.timedelta(days=tolerancia_dias)).strftime("%Y-%m-%d")
    q = ("SELECT id, fecha, importe, referencia, concepto FROM movimientos_tesoreria "
         "WHERE id_empresa=%s AND ABS(importe-%s)<0.01 AND fecha BETWEEN %s AND %s")
    p = [id_empresa, round(float(linea["importe"]), 2), desde, hasta]
    if id_cuenta is not None:
        q += " AND (id_cuenta=%s OR id_cuenta IS NULL)"; p.append(id_cuenta)
    out = []
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(q, p)
        for r in cur.fetchall():
            d = r if isinstance(r, dict) else dict(zip([c[0] for c in cur.description], r))
            if d["id"] in usados:
                continue
            # Puntuación: más cerca en fecha y coincidencia de referencia puntúan mejor.
            try:
                df = abs((_dt.datetime.strptime(str(d["fecha"])[:10], "%Y-%m-%d").date() - base).days)
            except Exception:
                df = tolerancia_dias
            ref_match = bool(linea.get("referencia") and d.get("referencia")
                             and linea["referencia"] == d["referencia"])
            d["_score"] = (0 if ref_match else 1, df)
            out.append(d)
    out.sort(key=lambda x: x["_score"])
    return out


def sugerir(id_linea, *, tolerancia_dias=3, id_cuenta=None, id_empresa=None) -> list:
    """Candidatos de movimiento para una línea (modo semiautomático)."""
    id_empresa = _emp(id_empresa)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM extracto_lineas WHERE id=%s AND id_empresa=%s",
                    (id_linea, id_empresa))
        r = cur.fetchone()
        if not r:
            return []
        linea = r if isinstance(r, dict) else dict(zip([c[0] for c in cur.description], r))
    usados = _CB.movimientos_ya_conciliados(id_empresa)
    return _candidatos({"fecha": linea["fecha"], "importe": float(linea["importe"]),
                        "referencia": linea.get("referencia")},
                       tolerancia_dias, usados, id_cuenta, id_empresa)


def conciliar(id_linea, id_movimiento, *, tipo="manual", usuario=None, id_empresa=None) -> bool:
    """Empareja una línea con un movimiento (manual). Calcula la diferencia de importe."""
    id_empresa = _emp(id_empresa)
    dif = 0.0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT importe FROM extracto_lineas WHERE id=%s AND id_empresa=%s",
                        (id_linea, id_empresa))
            rl = cur.fetchone()
            cur.execute("SELECT importe FROM movimientos_tesoreria WHERE id=%s AND id_empresa=%s",
                        (id_movimiento, id_empresa))
            rm = cur.fetchone()
        if rl and rm:
            il = float(rl[0] if not isinstance(rl, dict) else list(rl.values())[0])
            im = float(rm[0] if not isinstance(rm, dict) else list(rm.values())[0])
            dif = round(il - im, 2)
    except Exception as e:
        logger.debug("conciliar dif: %s", e)
    ok = _CB.marcar_conciliada(id_linea, id_movimiento, tipo, diferencia=dif,
                               usuario=usuario, id_empresa=id_empresa)
    if ok:
        _audit("concilia", f"linea={id_linea} mov={id_movimiento} ({tipo}) dif={dif}")
    return ok


def conciliar_automatico(id_extracto, *, tolerancia_dias=3, id_cuenta=None,
                         usuario=None, id_empresa=None) -> dict:
    """Empareja automáticamente las líneas con candidato ÚNICO. Devuelve un resumen."""
    id_empresa = _emp(id_empresa)
    res = {"conciliadas": 0, "ambiguas": 0, "sin_match": 0}
    usados = _CB.movimientos_ya_conciliados(id_empresa)
    for ln in _CB.listar_lineas(id_extracto, solo_no_conciliadas=True, id_empresa=id_empresa):
        cand = _candidatos({"fecha": ln["fecha"], "importe": float(ln["importe"]),
                            "referencia": ln.get("referencia")},
                           tolerancia_dias, usados, id_cuenta, id_empresa)
        if len(cand) == 1:
            if conciliar(ln["id"], cand[0]["id"], tipo="auto", usuario=usuario, id_empresa=id_empresa):
                usados.add(cand[0]["id"])
                res["conciliadas"] += 1
        elif len(cand) > 1:
            res["ambiguas"] += 1
        else:
            res["sin_match"] += 1
    return res


def diferencias(id_extracto, id_empresa=None) -> list:
    """Líneas del extracto sin conciliar (diferencias bancarias)."""
    id_empresa = _emp(id_empresa)
    return _CB.listar_lineas(id_extracto, solo_no_conciliadas=True, id_empresa=id_empresa)


def _audit(accion, detalles):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("sistema", accion, "conciliaciones", detalles)
    except Exception as e:
        logger.debug("audit %s: %s", accion, e)
