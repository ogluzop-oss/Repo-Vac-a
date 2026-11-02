"""
Motor de conciliación bancaria (rama Tesorería, FASE 8 + puntuación de confianza).

Importa extractos (CSV/N43/CAMT.053) y empareja sus líneas con los movimientos de tesorería
Y, directamente, con facturas de cliente/proveedor pendientes de cobro/pago, por importe +
fecha (tolerancia configurable) + similitud de texto (contrapartida). Cada candidato lleva una
puntuación de confianza 0-100% real (no decorativa, ver `_puntuacion`). Modos:
  • manual         → conciliar(linea, movimiento) explícito (solo movimientos_tesoreria), o
                      confirmar_candidato(linea, candidato) para cualquier tipo de candidato.
  • semiautomático → sugerir(linea) devuelve candidatos ordenados por puntuación (movimientos +
                      facturas de cliente/proveedor pendientes).
  • automático     → conciliar_automatico(extracto) empareja los casos no ambiguos.
Las líneas sin match quedan como diferencias.

Un candidato de tipo factura_cliente/factura_compra NO tiene fila propia en `movimientos_
tesoreria`; al confirmarlo se genera (idempotente, vía `db.tesoreria.registrar_movimiento`) el
movimiento bancario real y se registra el cobro/pago contra la factura (`facturas_cliente.
registrar_cobro` / `pagos_proveedor.registrar_pago`, motores ÚNICOS — N7), y SOLO ENTONCES se
reutiliza el `conciliar()` de siempre (marca la línea conciliada + contabiliza la diferencia si
la hay). No se duplica ningún motor de cobro/pago ni de contabilización.
"""

import datetime as _dt
import difflib
import logging

from src.db import conciliacion_bancaria as _CB
from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.tesoreria import extractos as _EX

logger = logging.getLogger("conciliacion_svc")

# Tolerancia relativa de importe para el decaimiento de la puntuación (0 dif = 100%, >= esta
# fracción del importe de la línea = 0 puntos de importe). El filtrado SQL previo usa una banda
# más ancha (el doble) para no descartar en la base de datos candidatos que aún puntúen > 0.
_TOL_IMPORTE_PCT = 0.03


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.tesoreria.identidad_tesoreria import empresa_id
        return empresa_id(id_empresa)
    except Exception:
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


def _fecha_a_date(f):
    """Normaliza fecha/datetime/str a `date` (mismo criterio que el `_candidatos` original)."""
    if isinstance(f, _dt.datetime):
        return f.date()
    if isinstance(f, _dt.date):
        return f
    if hasattr(f, "strftime"):
        f = f.strftime("%Y-%m-%d")
    return _dt.datetime.strptime(str(f)[:10], "%Y-%m-%d").date()


def _texto(*partes) -> str:
    return " ".join(str(p).strip() for p in partes if p).lower()


def _puntuacion(importe_linea, importe_cand, dias_dif, tolerancia_dias, texto_linea, texto_cand) -> float:
    """Puntuación de confianza 0-100% real (no decorativa), combinando tres señales:
      • Importe (50 pts): coincidencia exacta (±0.01) = 50; decae linealmente a 0 cuando la
        diferencia relativa alcanza `_TOL_IMPORTE_PCT` del importe de la línea.
      • Fecha (30 pts): mismo día = 30; decae linealmente a 0 en el límite de `tolerancia_dias`.
      • Similitud de texto (20 pts): `difflib.SequenceMatcher` sobre concepto/referencia vs.
        nombre de la contrapartida (razón social/nombre cliente) o número de factura — 20·ratio.
    Se usa para ORDENAR y para MOSTRAR (la GUI pinta el número real, no un orden decorativo)."""
    il = abs(float(importe_linea or 0))
    ic = abs(float(importe_cand or 0))
    dif_imp = abs(il - ic)
    if dif_imp <= 0.01:
        p_importe = 50.0
    else:
        base = max(il, 0.01)
        pct = dif_imp / base
        p_importe = 50.0 * max(0.0, 1.0 - pct / _TOL_IMPORTE_PCT)
    if tolerancia_dias and tolerancia_dias > 0:
        p_fecha = 30.0 * max(0.0, 1.0 - (abs(dias_dif) / tolerancia_dias))
    else:
        p_fecha = 30.0 if dias_dif == 0 else 0.0
    t1, t2 = (texto_linea or "").strip().lower(), (texto_cand or "").strip().lower()
    sim = difflib.SequenceMatcher(None, t1, t2).ratio() if t1 and t2 else 0.0
    p_texto = 20.0 * sim
    return round(max(0.0, min(100.0, p_importe + p_fecha + p_texto)), 1)


def _candidatos_movimientos(linea, base, tolerancia_dias, usados, id_cuenta, id_empresa):
    """Movimientos de tesorería que casan por importe exacto y fecha ±tolerancia."""
    desde = (base - _dt.timedelta(days=tolerancia_dias)).strftime("%Y-%m-%d")
    hasta = (base + _dt.timedelta(days=tolerancia_dias)).strftime("%Y-%m-%d")
    q = ("SELECT id, fecha, importe, referencia, concepto FROM movimientos_tesoreria "
         "WHERE id_empresa=%s AND ABS(importe-%s)<0.01 AND fecha BETWEEN %s AND %s")
    p = [id_empresa, round(float(linea["importe"]), 2), desde, hasta]
    if id_cuenta is not None:
        q += " AND (id_cuenta=%s OR id_cuenta IS NULL)"; p.append(id_cuenta)
    texto_linea = _texto(linea.get("concepto"), linea.get("referencia"))
    out = []
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(q, p)
        for r in cur.fetchall():
            d = r if isinstance(r, dict) else dict(zip([c[0] for c in cur.description], r))
            if d["id"] in usados:
                continue
            try:
                df = abs((_fecha_a_date(d["fecha"]) - base).days)
            except Exception:
                df = tolerancia_dias
            score = _puntuacion(linea["importe"], d["importe"], df, tolerancia_dias,
                                texto_linea, _texto(d.get("concepto"), d.get("referencia")))
            d["tipo"] = "movimiento"
            d["score"] = score
            d["etiqueta"] = f"Mov. #{d['id']} · {d.get('concepto') or d.get('referencia') or ''}"
            out.append(d)
    return out


def _candidatos_facturas_cliente(linea, base, tolerancia_dias, id_empresa):
    """Facturas de cliente pendientes de cobro que casan por importe (±tolerancia relativa).
    Solo aplica a líneas de ABONO (importe > 0: dinero que entra = cobro)."""
    if float(linea["importe"] or 0) <= 0:
        return []
    from src.db import facturas_cliente as _FC
    importe = abs(float(linea["importe"]))
    banda = max(importe * _TOL_IMPORTE_PCT * 2, 1.0)
    texto_linea = _texto(linea.get("concepto"), linea.get("referencia"))
    out = []
    for f in _FC.listar_pendientes_cobro(id_empresa=id_empresa, importe_min=importe - banda,
                                         importe_max=importe + banda):
        fv = f.get("fecha_vencimiento") or f.get("fecha_emision")
        try:
            df = abs((_fecha_a_date(fv) - base).days) if fv else tolerancia_dias
        except Exception:
            df = tolerancia_dias
        texto_cand = _texto(f.get("cliente_nombre"), f.get("numero"), f.get("serie"))
        score = _puntuacion(importe, f["pendiente"], df, tolerancia_dias, texto_linea, texto_cand)
        out.append({"id": f["id_factura"], "tipo": "factura_cliente", "fecha": fv,
                    "importe": float(f["pendiente"]), "referencia": f.get("numero"),
                    "concepto": f"Factura cliente {f.get('serie') or ''}{f.get('numero') or ''} · "
                                f"{f.get('cliente_nombre') or ''}".strip(),
                    "id_cliente": f.get("id_cliente"), "score": score,
                    "etiqueta": f"Factura cliente #{f['id_factura']} · {f.get('cliente_nombre') or ''} · "
                               f"{float(f['pendiente']):.2f} €"})
    return out


def _candidatos_facturas_compra(linea, base, tolerancia_dias, id_empresa):
    """Facturas de proveedor pendientes de pago que casan por importe (±tolerancia relativa).
    Solo aplica a líneas de CARGO (importe < 0: dinero que sale = pago)."""
    if float(linea["importe"] or 0) >= 0:
        return []
    from src.db import pagos_proveedor as _PP
    importe = abs(float(linea["importe"]))
    banda = max(importe * _TOL_IMPORTE_PCT * 2, 1.0)
    texto_linea = _texto(linea.get("concepto"), linea.get("referencia"))
    out = []
    for f in _PP.listar_pendientes_pago(id_empresa=id_empresa, importe_min=importe - banda,
                                        importe_max=importe + banda):
        fv = f.get("fecha_factura")
        try:
            df = abs((_fecha_a_date(fv) - base).days) if fv else tolerancia_dias
        except Exception:
            df = tolerancia_dias
        texto_cand = _texto(f.get("proveedor"), f.get("numero_factura"))
        score = _puntuacion(importe, f["pendiente"], df, tolerancia_dias, texto_linea, texto_cand)
        out.append({"id": f["id_factura"], "tipo": "factura_compra", "fecha": fv,
                    "importe": -float(f["pendiente"]), "referencia": f.get("numero_factura"),
                    "concepto": f"Factura proveedor {f.get('numero_factura') or ''} · "
                                f"{f.get('proveedor') or ''}".strip(),
                    "id_proveedor": f.get("id_proveedor"), "score": score,
                    "etiqueta": f"Factura proveedor #{f['id_factura']} · {f.get('proveedor') or ''} · "
                               f"{float(f['pendiente']):.2f} €"})
    return out


def _candidatos(linea, tolerancia_dias, usados, id_cuenta, id_empresa):
    """Todos los candidatos (movimientos + facturas pendientes de cliente/proveedor),
    puntuados 0-100% y ordenados de mayor a menor confianza."""
    f = linea["fecha"]
    base = _fecha_a_date(f)
    out = _candidatos_movimientos(linea, base, tolerancia_dias, usados, id_cuenta, id_empresa)
    out += _candidatos_facturas_cliente(linea, base, tolerancia_dias, id_empresa)
    out += _candidatos_facturas_compra(linea, base, tolerancia_dias, id_empresa)
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def sugerir(id_linea, *, tolerancia_dias=3, id_cuenta=None, id_empresa=None) -> list:
    """Candidatos para una línea (modo semiautomático): movimientos de tesorería Y facturas de
    cliente/proveedor pendientes, cada uno con su puntuación de confianza 0-100% real."""
    id_empresa = _emp(id_empresa)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM extracto_lineas WHERE id=%s AND id_empresa=%s",
                    (id_linea, id_empresa))
        r = cur.fetchone()
        if not r:
            return []
        linea = r if isinstance(r, dict) else dict(zip([c[0] for c in cur.description], r))
    if id_cuenta is None:
        id_cuenta = linea.get("id_extracto") and _cuenta_de_extracto(linea["id_extracto"], id_empresa)
    usados = _CB.movimientos_ya_conciliados(id_empresa)
    return _candidatos({"fecha": linea["fecha"], "importe": float(linea["importe"]),
                        "referencia": linea.get("referencia"), "concepto": linea.get("concepto")},
                       tolerancia_dias, usados, id_cuenta, id_empresa)


def _cuenta_de_extracto(id_extracto, id_empresa):
    """Resuelve la cuenta bancaria del extracto (para el movimiento sintético de una factura)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_cuenta FROM extractos_bancarios WHERE id=%s AND id_empresa=%s",
                        (id_extracto, id_empresa))
            r = cur.fetchone()
            return (r[0] if r and not isinstance(r, dict) else (r.get("id_cuenta") if r else None))
    except Exception as e:
        logger.debug("_cuenta_de_extracto: %s", e)
        return None


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
        # FASE 10 — asiento contable de la diferencia bancaria (idempotente, solo si dif != 0).
        if dif:
            try:
                from src.services.tesoreria import contabilidad as _TC
                _TC.contabilizar_diferencia_conciliacion(id_linea, _hoy(), dif, id_empresa=id_empresa)
            except Exception as e:
                logger.debug("contab diferencia: %s", e)
    return ok


def _hoy():
    return _dt.date.today().strftime("%Y-%m-%d")


def _liquidar_factura(id_linea, candidato, tipo_cand, usuario, id_empresa, id_cuenta):
    """Genera el movimiento bancario REAL de una factura (idempotente, vía
    `tesoreria.registrar_movimiento`) y registra el cobro/pago contra ella reutilizando los
    motores únicos (`facturas_cliente.registrar_cobro` / `pagos_proveedor.registrar_pago`, N7 —
    nunca un segundo motor de cobros/pagos). Devuelve el id del movimiento o None si no se pudo
    o si ese movimiento ya estaba conciliado (evita doble liquidación en reintentos).

    IMPORTANTE: el importe real es el de la LÍNEA DEL EXTRACTO (lo que realmente entró/salió del
    banco), NUNCA el pendiente de la factura — si solo coincide por tolerancia (p.ej. una
    comisión bancaria ya descontada), se liquida un cobro/pago PARCIAL por el importe real
    (`registrar_cobro`/`registrar_pago` ya saben dejar la factura en estado 'parcial'); así el
    movimiento bancario y la línea casan EXACTO (diferencia de conciliación = 0) y el resto
    pendiente de la factura queda correctamente abierto, en vez de inventar un cobro que nunca
    se produjo."""
    from src.db import tesoreria as _TES
    id_factura = candidato["id"]
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT fecha, referencia, importe FROM extracto_lineas WHERE id=%s AND id_empresa=%s",
                    (id_linea, id_empresa))
        rl = cur.fetchone()
    if not rl:
        return None
    fecha = (rl.get("fecha") if isinstance(rl, dict) else rl[0])
    referencia_linea = (rl.get("referencia") if isinstance(rl, dict) else rl[1])
    importe_real = round(abs(float(rl.get("importe") if isinstance(rl, dict) else rl[2])), 2)
    es_cobro = tipo_cand == "factura_cliente"
    tipo_mov = "COBRO" if es_cobro else "PAGO"
    origen = "factura_cliente" if es_cobro else "factura_compra"
    doc = f"FC:{id_factura}" if es_cobro else f"FCMP:{id_factura}"
    try:
        mov_id = _TES.registrar_movimiento(
            tipo_mov, importe_real if es_cobro else -importe_real, id_cuenta=id_cuenta,
            fecha=fecha, concepto=candidato.get("concepto"), referencia=referencia_linea,
            origen=origen, id_documento=doc, idempotente=True, usuario=usuario,
            id_empresa=id_empresa)
        if mov_id is None:
            return None
        # Si este movimiento ya está conciliado (reintento tras un confirmar previo), NO se
        # vuelve a registrar el cobro/pago — se delega en `conciliar()` para el error esperado.
        if mov_id in _CB.movimientos_ya_conciliados(id_empresa):
            logger.info("_liquidar_factura: movimiento %s ya conciliado, omito doble liquidación", mov_id)
            return None
        if es_cobro:
            from src.db import facturas_cliente as _FC
            r = _FC.registrar_cobro(id_factura, importe_real, forma_pago="transferencia",
                                    referencia=referencia_linea or f"CONC:{id_linea}",
                                    id_empresa=id_empresa)
            if not r.get("ok"):
                return None
        else:
            from src.db import pagos_proveedor as _PP
            pid = _PP.registrar_pago(id_factura, "transferencia", importe_real,
                                     id_proveedor=candidato.get("id_proveedor"),
                                     referencia=referencia_linea or f"CONC:{id_linea}",
                                     id_empresa=id_empresa, usuario=usuario)
            if pid is None:
                return None
        return mov_id
    except Exception as e:
        logger.error("_liquidar_factura(%s,%s): %s", id_linea, tipo_cand, e)
        return None


def confirmar_candidato(id_linea, candidato, *, tipo="manual", usuario=None, id_empresa=None,
                        id_cuenta=None) -> int | None:
    """Confirma UN candidato devuelto por `sugerir()` — de cualquier tipo (movimiento de
    tesorería, factura de cliente o de proveedor) — para una línea de extracto. Punto de entrada
    ÚNICO de confirmación (lo usan el botón «Aprobar Conciliación», el emparejamiento manual y
    `conciliar_automatico`). Si el candidato es una factura, primero la liquida (ver
    `_liquidar_factura`) y SOLO ENTONCES reutiliza `conciliar()` de siempre (marca la línea
    conciliada + contabiliza la diferencia bancaria si la hay — mismo camino de siempre, sin
    motor paralelo). Devuelve el id del movimiento de tesorería (real o recién generado) si la
    conciliación se completó, o None."""
    id_empresa = _emp(id_empresa)
    tipo_cand = (candidato or {}).get("tipo", "movimiento")
    if tipo_cand == "movimiento":
        id_mov = candidato["id"]
    else:
        if id_cuenta is None:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT id_extracto FROM extracto_lineas WHERE id=%s AND id_empresa=%s",
                            (id_linea, id_empresa))
                r = cur.fetchone()
            eid = (r.get("id_extracto") if r and isinstance(r, dict) else (r[0] if r else None))
            id_cuenta = eid and _cuenta_de_extracto(eid, id_empresa)
        id_mov = _liquidar_factura(id_linea, candidato, tipo_cand, usuario, id_empresa, id_cuenta)
        if id_mov is None:
            return None
    return id_mov if conciliar(id_linea, id_mov, tipo=tipo, usuario=usuario, id_empresa=id_empresa) else None


#: Puntuación mínima para que `conciliar_automatico` confirme SOLO (sin intervención humana) un
#: candidato único. Antes de la puntuación, "candidato único" ya implicaba alta confianza (solo
#: movimientos por importe EXACTO ±0.01); ahora que `_candidatos` también admite facturas por
#: importe aproximado, un único candidato ya NO es necesariamente de fiar (p.ej. una línea sin
#: relación real podría caer, por pura coincidencia, dentro de la banda de una factura pendiente
#: de importe parecido) — se exige además una puntuación alta antes de tocar nada automáticamente.
_UMBRAL_AUTO = 70.0


def conciliar_automatico(id_extracto, *, tolerancia_dias=3, id_cuenta=None,
                         usuario=None, id_empresa=None) -> dict:
    """Empareja automáticamente las líneas con candidato ÚNICO Y de confianza alta
    (score >= `_UMBRAL_AUTO`) — movimiento o factura pendiente de cliente/proveedor. Un único
    candidato de baja confianza NO se toca (queda como diferencia, para `_aprobar_conciliacion`/
    `confirmar_candidato` manual). Devuelve un resumen."""
    id_empresa = _emp(id_empresa)
    if id_cuenta is None:
        id_cuenta = _cuenta_de_extracto(id_extracto, id_empresa)
    res = {"conciliadas": 0, "ambiguas": 0, "sin_match": 0}
    usados = _CB.movimientos_ya_conciliados(id_empresa)
    for ln in _CB.listar_lineas(id_extracto, solo_no_conciliadas=True, id_empresa=id_empresa):
        cand = _candidatos({"fecha": ln["fecha"], "importe": float(ln["importe"]),
                            "referencia": ln.get("referencia"), "concepto": ln.get("concepto")},
                           tolerancia_dias, usados, id_cuenta, id_empresa)
        if len(cand) == 1 and cand[0]["score"] >= _UMBRAL_AUTO:
            id_mov = confirmar_candidato(ln["id"], cand[0], tipo="auto", usuario=usuario,
                                         id_empresa=id_empresa, id_cuenta=id_cuenta)
            if id_mov is not None:
                usados.add(id_mov)
                res["conciliadas"] += 1
            else:
                res["sin_match"] += 1
        elif len(cand) == 1:
            # Único candidato, pero de confianza insuficiente: no se auto-concilia.
            res["sin_match"] += 1
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
