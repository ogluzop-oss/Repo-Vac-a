"""
Posting contable asíncrono (E6.4/E6.5) — cola + generación de asientos.

DC2: COLA ASÍNCRONA + AGREGACIÓN DIARIA. Los eventos del ERP (ventas, compras,
devoluciones) se ENCOLAN (best-effort, sin bloquear la operación) y un procesador
genera los asientos: tickets de TPV → 1 asiento resumen por día; facturas → 1 por
documento. Idempotente; nunca rompe la venta/compra.
"""

import datetime as _dt
import json
import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _filas_a_dicts, ensure_schema,
                             obtener_conexion)
from src.services.contabilidad import asientos as A
from src.services.contabilidad import cuentas as K
from src.services.contabilidad import mapeo as M

logger = logging.getLogger("contab.posting")


def _empresa(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.contabilidad.identidad_contabilidad import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        if id_empresa:
            return id_empresa
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return EMPRESA_DEFAULT_ID


def _fecha(f):
    if isinstance(f, (_dt.date, _dt.datetime)):
        return f.strftime("%Y-%m-%d")
    return str(f)[:10]


def _desglose(total, id_empresa):
    """(base, cuota, tipo_iva) IVA-incluido, usando la MISMA fuente fiscal."""
    try:
        from src.utils import fiscalidad
        d = fiscalidad.desglose_iva(total, id_empresa=id_empresa)
        return round(d["base"], 2), round(d["cuota"], 2), d["tipo"]
    except Exception:
        base = round(float(total or 0), 2)
        return base, 0.0, 0.0


# ── Encolado (desde hooks del ERP) ────────────────────────────────────────────
def encolar(evento, ref, total, fecha, subtipo=None, extra=None, id_empresa=None) -> int | None:
    """Encola un evento económico SOLO si la contabilidad está activa. Best-effort."""
    id_empresa = _empresa(id_empresa)
    if not K.contabilidad_activa(id_empresa):
        return None
    payload = {"total": round(float(total or 0), 2)}
    if extra:
        payload.update(extra)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            # M1: idempotencia — una referencia = un evento. Si ya existe (cualquier
            # estado), no se vuelve a encolar (evita doble clic / reintentos).
            cur.execute("SELECT id FROM contab_cola WHERE id_empresa=%s AND evento=%s AND ref=%s "
                        "LIMIT 1", (id_empresa, evento, str(ref)))
            ya = cur.fetchone()
            if ya:
                return ya[0] if not isinstance(ya, dict) else list(ya.values())[0]
            cur.execute("INSERT INTO contab_cola (id_empresa, evento, subtipo, ref, fecha_evento, "
                        "payload) VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_empresa, evento, subtipo, str(ref), _fecha(fecha),
                         json.dumps(payload, ensure_ascii=False)))
            cid = cur.lastrowid
            conn.commit()
            return cid
    except Exception as e:
        logger.warning("encolar(%s,%s): %s", evento, ref, e)
        return None


def encolar_venta(ref, total, fecha, forma_pago="efectivo", subtipo="ticket", id_empresa=None,
                  base=None, iva=None):
    """`base`/`iva` (FASE B): desglose YA resuelto (multi-tipo/ISP/exento) a pasar tal cual
    al asiento — mismo parámetro que ya admite `encolar_compra`. Si se omiten (caso normal
    de los tickets TPV), el procesador sigue calculando el desglose por el tipo de IVA de
    la empresa (`_desglose`), sin cambio de comportamiento."""
    extra = {"forma_pago": forma_pago}
    if base is not None:
        extra["base"] = round(float(base), 2)
    if iva is not None:
        extra["iva"] = round(float(iva), 2)
    return encolar("venta", ref, total, fecha, subtipo=subtipo, extra=extra, id_empresa=id_empresa)


def encolar_compra(ref, total, fecha, id_empresa=None, base=None, iva=None, subtipo="factura",
                   retencion=None):
    extra = {}
    if base is not None:
        extra["base"] = round(float(base), 2)
    if iva is not None:
        extra["iva"] = round(float(iva), 2)
    if retencion:
        extra["retencion"] = round(float(retencion), 2)
    return encolar("compra", ref, total, fecha, subtipo=subtipo, extra=extra, id_empresa=id_empresa)


def encolar_devolucion(ref, total, fecha, tipo="venta", forma_pago="efectivo", id_empresa=None):
    """Devolución de venta (o de compra) → contraflujo del importe."""
    return encolar("devolucion", ref, total, fecha, subtipo=tipo,
                   extra={"forma_pago": forma_pago}, id_empresa=id_empresa)


def encolar_nomina(ref, fecha, total_devengado, ss_empresa, ss_trabajador, irpf,
                   id_empresa=None):
    """Encola una nómina (F4.5). El payload lleva las magnitudes ya calculadas por el
    motor (la contabilidad no depende de RRHH para construir el asiento). Best-effort."""
    return encolar("nomina", ref, total_devengado, fecha, subtipo="nomina",
                   extra={"total_devengado": round(float(total_devengado or 0), 2),
                          "ss_empresa": round(float(ss_empresa or 0), 2),
                          "ss_trabajador": round(float(ss_trabajador or 0), 2),
                          "irpf": round(float(irpf or 0), 2)},
                   id_empresa=id_empresa)


# ── Procesado de la cola → asientos ──────────────────────────────────────────
def _pendientes(cur, id_empresa, evento):
    cur.execute("SELECT * FROM contab_cola WHERE id_empresa=%s AND evento=%s AND estado='pendiente' "
                "ORDER BY fecha_evento, id", (id_empresa, evento))
    return _filas_a_dicts(cur, cur.fetchall())


def _marcar(cur, ids, id_asiento):
    if not ids:
        return
    marks = ",".join(["%s"] * len(ids))
    cur.execute(f"UPDATE contab_cola SET estado='hecho', id_asiento=%s WHERE id IN ({marks})",
                (id_asiento, *ids))


def _anio_evento(ev) -> int:
    return int(_fecha(ev.get("fecha_evento"))[:4])


def _separar_bloqueados_por_cierre(eventos, id_empresa):
    """Parte `eventos` en (procesables, bloqueados): un evento está BLOQUEADO si su ejercicio
    (el año de `fecha_evento`) ya está cerrado — en ese caso `crear_asiento` SIEMPRE lo va a
    rechazar (ver `asientos.crear_asiento`: `if K.ejercicio_cerrado(...): return None`), así que
    jamás se procesará solo porque se reintente otra vez.

    Bug real corregido aquí: antes de esto, un evento así se quedaba en estado 'pendiente' para
    siempre (`crear_asiento` devuelve `None` → nunca se llama a `_cerrar`/`_marcar`, que es lo
    único que saca un evento de 'pendiente') — `procesar_cola()` se ejecuta en CADA arranque de
    la app (`src/main.py`, hook H6), así que ese mismo evento se reintentaba y volvía a fallar con
    el mismo warning en CADA arranque, para siempre, sin que nadie lo notara ni pudiera hacer nada
    al respecto. Ahora se separa ANTES de intentarlo, se marca `estado='error'` (ya contemplado en
    el propio esquema de `contab_cola`, nunca antes usado) con un `ultimo_error` explicativo, y
    deja de reintentarse — pero NO se pierde: `listar_bloqueados_por_cierre`/`reintentar_bloqueado`
    permiten revisarlo y re-encolarlo manualmente (p. ej. si se reabre el ejercicio)."""
    procesables, bloqueados = [], []
    for ev in eventos:
        if K.ejercicio_cerrado(_anio_evento(ev), id_empresa):
            bloqueados.append(ev)
        else:
            procesables.append(ev)
    return procesables, bloqueados


def _marcar_bloqueados(id_empresa, eventos):
    if not eventos:
        return
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for ev in eventos:
                motivo = (f"Ejercicio {_anio_evento(ev)} cerrado — requiere revisión manual "
                          f"(reabrir el ejercicio y reintentar, o descartar).")
                cur.execute(
                    "UPDATE contab_cola SET estado='error', ultimo_error=%s, "
                    "intentos=intentos+1 WHERE id=%s AND id_empresa=%s",
                    (motivo[:300], ev["id"], id_empresa))
            conn.commit()
    except Exception as e:
        logger.error("_marcar_bloqueados: %s", e)


def listar_bloqueados_por_cierre(id_empresa=None) -> list:
    """Eventos de la cola marcados `estado='error'` por ejercicio cerrado — para una pantalla de
    revisión manual (p. ej. Contabilidad → Cola). Más recientes primero."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM contab_cola WHERE id_empresa=%s AND estado='error' "
                        "ORDER BY fecha_evento DESC, id DESC", (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_bloqueados_por_cierre: %s", e)
        return []


def reintentar_bloqueado(id_cola, id_empresa=None) -> bool:
    """Devuelve un evento marcado `estado='error'` a `pendiente` (p. ej. tras reabrir su
    ejercicio) para que el próximo `procesar_cola()` lo vuelva a intentar. No reintenta un evento
    que no esté en 'error' (protege de reencolar algo ya `hecho`)."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE contab_cola SET estado='pendiente' "
                        "WHERE id=%s AND id_empresa=%s AND estado='error'", (id_cola, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
        return ok
    except Exception as e:
        logger.error("reintentar_bloqueado(%s): %s", id_cola, e)
        return False


def procesar_cola(id_empresa=None, incluir_nominas=True) -> dict:
    """Genera asientos de los eventos pendientes. Tickets → 1 asiento/día; facturas
    (venta/compra) → 1 por documento. Devuelve {asientos, eventos, ventas, compras,
    devoluciones, nominas, bloqueados} (contadores de asientos por tipo; `bloqueados` = eventos
    cuyo ejercicio ya cerró, marcados para revisión manual en vez de reintentarse para siempre).

    `incluir_nominas=False` deja las nóminas EN COLA (las procesa la contabilidad general):
    lo usa el CIERRE DIARIO de caja, que recopila los hechos económicos del día EXCEPTO
    las nóminas (no son un hecho de caja)."""
    id_empresa = _empresa(id_empresa)
    res = {"asientos": 0, "eventos": 0, "ventas": 0, "compras": 0, "devoluciones": 0, "nominas": 0,
           "bloqueados": 0}
    if not K.contabilidad_activa(id_empresa):
        return res
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            ventas = _pendientes(cur, id_empresa, "venta")
            compras = _pendientes(cur, id_empresa, "compra")
            devoluciones = _pendientes(cur, id_empresa, "devolucion")
            nominas = _pendientes(cur, id_empresa, "nomina") if incluir_nominas else []
    except Exception as e:
        logger.error("procesar_cola/listar: %s", e)
        return res

    ventas, bloq_v = _separar_bloqueados_por_cierre(ventas, id_empresa)
    compras, bloq_c = _separar_bloqueados_por_cierre(compras, id_empresa)
    devoluciones, bloq_d = _separar_bloqueados_por_cierre(devoluciones, id_empresa)
    nominas, bloq_n = _separar_bloqueados_por_cierre(nominas, id_empresa)
    bloqueados = bloq_v + bloq_c + bloq_d + bloq_n
    if bloqueados:
        _marcar_bloqueados(id_empresa, bloqueados)
        res["bloqueados"] = len(bloqueados)

    # ── Ventas ──
    tickets_por_fecha = {}
    for ev in ventas:
        p = _payload(ev)
        if ev.get("subtipo") == "factura":
            aid = _asiento_venta_factura(ev, p, id_empresa)
            if aid:
                _cerrar(id_empresa, [ev["id"]], aid)
                res["asientos"] += 1; res["eventos"] += 1; res["ventas"] += 1
        else:
            tickets_por_fecha.setdefault(ev["fecha_evento"], []).append(ev)
    for fecha, evs in tickets_por_fecha.items():
        aid = _asiento_tickets_dia(fecha, evs, id_empresa)
        if aid:
            _cerrar(id_empresa, [e["id"] for e in evs], aid)
            res["asientos"] += 1; res["eventos"] += len(evs); res["ventas"] += 1

    # ── Compras ── (1 asiento por factura) — E6.5
    for ev in compras:
        p = _payload(ev)
        aid = _asiento_compra(ev, p, id_empresa)
        if aid:
            _cerrar(id_empresa, [ev["id"]], aid)
            res["asientos"] += 1; res["eventos"] += 1; res["compras"] += 1

    # ── Devoluciones ── (1 asiento por devolución) — E6.5
    for ev in devoluciones:
        p = _payload(ev)
        aid = _asiento_devolucion(ev, p, id_empresa)
        if aid:
            _cerrar(id_empresa, [ev["id"]], aid)
            res["asientos"] += 1; res["eventos"] += 1; res["devoluciones"] += 1

    # ── Nóminas ── (1 asiento por nómina) — F4.5. Se omiten si incluir_nominas=False.
    for ev in nominas:
        p = _payload(ev)
        aid = _asiento_nomina(ev, p, id_empresa)
        if aid:
            _cerrar(id_empresa, [ev["id"]], aid)
            res["asientos"] += 1; res["eventos"] += 1; res["nominas"] += 1
    return res


def _payload(ev) -> dict:
    try:
        return json.loads(ev.get("payload") or "{}")
    except Exception:
        return {}


def _cerrar(id_empresa, ids, id_asiento):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            _marcar(cur, ids, id_asiento)
            conn.commit()
    except Exception as e:
        logger.error("_cerrar: %s", e)


def _asiento_tickets_dia(fecha, eventos, id_empresa):
    """1 asiento resumen del día: Debe formas de pago · Haber 700 (base) + 477 (cuota)."""
    por_fp, total = {}, 0.0
    for ev in eventos:
        p = _payload(ev)
        t = round(float(p.get("total") or 0), 2)
        fp = (p.get("forma_pago") or "efectivo")
        por_fp[fp] = round(por_fp.get(fp, 0.0) + t, 2); total += t
    total = round(total, 2)
    base, cuota, tipo = _desglose(total, id_empresa)
    lineas = [{"codigo_cuenta": M.cuenta_forma_pago(fp, id_empresa), "debe": imp,
               "descripcion": f"Ventas {fp} {fecha}"} for fp, imp in por_fp.items()]
    lineas.append({"codigo_cuenta": M.cuenta("venta", id_empresa=id_empresa), "haber": base,
                   "descripcion": "Ventas del día"})
    if cuota:
        lineas.append({"codigo_cuenta": M.cuenta("iva_rep", id_empresa=id_empresa), "haber": cuota,
                       "tipo_iva": tipo, "descripcion": "IVA repercutido"})
    r = A.crear_asiento(fecha, lineas, concepto=f"Ventas TPV {fecha}", origen="venta",
                        ref_origen=f"tickets:{fecha}", id_empresa=id_empresa)
    return r["id"] if r else None


def _asiento_venta_factura(ev, p, id_empresa):
    total = round(float(p.get("total") or 0), 2)
    # FASE B: si el evento trae base/iva YA resueltos (facturas_cliente ya aplicó el motor
    # fiscal único —multi-tipo/ISP/intracom/exento—), se usan tal cual; si no (p. ej. un
    # futuro llamador que no los calcule), se cae al desglose por el IVA de la empresa.
    base = p.get("base"); cuota = p.get("iva")
    if base is None:
        base, cuota, tipo = _desglose(total, id_empresa)
    else:
        base = round(float(base), 2)
        cuota = round(float(cuota if cuota is not None else (total - base)), 2)
        tipo = round(cuota / base * 100, 2) if base else 0.0
    fp = p.get("forma_pago") or "factura"
    lineas = [{"codigo_cuenta": M.cuenta_forma_pago(fp, id_empresa), "debe": total,
               "descripcion": "Cobro/cliente"},
              {"codigo_cuenta": M.cuenta("venta", id_empresa=id_empresa), "haber": base}]
    if cuota:
        lineas.append({"codigo_cuenta": M.cuenta("iva_rep", id_empresa=id_empresa), "haber": cuota,
                       "tipo_iva": tipo})
    r = A.crear_asiento(ev["fecha_evento"], lineas, concepto=f"Factura venta {ev['ref']}",
                        origen="venta", ref_origen=f"factura:{ev['ref']}", id_empresa=id_empresa, idempotente=True)
    return r["id"] if r else None


def _asiento_compra(ev, p, id_empresa):
    total = round(float(p.get("total") or 0), 2)
    base = p.get("base"); iva = p.get("iva")
    if base is None:
        base, iva, _ = _desglose(total, id_empresa)
    base = round(float(base), 2); iva = round(float(iva or (total - base)), 2)
    tipo_iva = round(iva / base * 100, 2) if base else 0.0
    lineas = [{"codigo_cuenta": M.cuenta("compra", id_empresa=id_empresa), "debe": base,
               "descripcion": "Compra"}]
    if iva:
        lineas.append({"codigo_cuenta": M.cuenta("iva_sop", id_empresa=id_empresa), "debe": iva,
                       "tipo_iva": tipo_iva, "descripcion": "IVA soportado"})
    # AEAT-3: retención IRPF de profesionales (4751 HP acreedora). El proveedor se reduce en la
    # retención y se abona a 4751. Sin retención el asiento es idéntico al anterior.
    retencion = round(float(p.get("retencion") or 0), 2)
    lineas.append({"codigo_cuenta": M.cuenta("proveedor", id_empresa=id_empresa),
                   "haber": round(base + iva - retencion, 2), "descripcion": "Proveedor"})
    if retencion:
        lineas.append({"codigo_cuenta": "4751", "haber": retencion,
                       "descripcion": "HP acreedora retenciones IRPF"})
    r = A.crear_asiento(ev["fecha_evento"], lineas, concepto=f"Factura compra {ev['ref']}",
                        origen="compra", ref_origen=f"compra:{ev['ref']}", id_empresa=id_empresa, idempotente=True)
    return r["id"] if r else None


def _asiento_devolucion(ev, p, id_empresa):
    """Devolución de venta: contraflujo (Debe 708 base + 477 cuota / Haber forma_pago).
    Devolución de compra: (Debe 400 / Haber 608 base + 472 cuota)."""
    total = round(float(p.get("total") or 0), 2)
    base, cuota, tipo = _desglose(total, id_empresa)
    if ev.get("subtipo") == "compra":
        lineas = [{"codigo_cuenta": M.cuenta("proveedor", id_empresa=id_empresa), "debe": total},
                  {"codigo_cuenta": M.cuenta("devolucion_compra", id_empresa=id_empresa), "haber": base}]
        if cuota:
            lineas.append({"codigo_cuenta": M.cuenta("iva_sop", id_empresa=id_empresa), "haber": cuota,
                           "tipo_iva": tipo})
        concepto = f"Devolución de compra {ev['ref']}"
    else:
        fp = p.get("forma_pago") or "efectivo"
        lineas = [{"codigo_cuenta": M.cuenta("devolucion_venta", id_empresa=id_empresa), "debe": base},
                  {"codigo_cuenta": M.cuenta_forma_pago(fp, id_empresa), "haber": total}]
        if cuota:
            lineas.insert(1, {"codigo_cuenta": M.cuenta("iva_rep", id_empresa=id_empresa),
                              "debe": cuota, "tipo_iva": tipo})
        concepto = f"Devolución de venta {ev['ref']}"
    r = A.crear_asiento(ev["fecha_evento"], lineas, concepto=concepto, origen="devolucion",
                        ref_origen=f"devolucion:{ev['ref']}", id_empresa=id_empresa, idempotente=True)
    return r["id"] if r else None


def _asegurar_cuenta_4751(id_empresa):
    """Crea la 4751 (HP acreedora por IRPF) si la empresa fue activada antes de F4.5.
    Idempotente: solo crea si falta."""
    try:
        if not K.obtener_cuenta("4751", id_empresa):
            K.crear_cuenta("4751", "Hacienda Pública, acreedora por retenciones practicadas (IRPF)",
                           tipo="pasivo", naturaleza="acreedora", id_empresa=id_empresa)
    except Exception as e:
        logger.warning("_asegurar_cuenta_4751(%s): %s", id_empresa, e)


def _asiento_nomina(ev, p, id_empresa):
    """Asiento de nómina (F4.5). Debe 640 (devengado) + 642 (SS empresa) /
    Haber 476 (SS empresa+trabajador) + 4751 (IRPF) + 465 (líquido). Cuadre exacto."""
    dev = round(float(p.get("total_devengado") or p.get("total") or 0), 2)
    if dev <= 0:
        return None
    ss_e = round(float(p.get("ss_empresa") or 0), 2)
    ss_t = round(float(p.get("ss_trabajador") or 0), 2)
    irpf = round(float(p.get("irpf") or 0), 2)
    liquido = round(dev - ss_t - irpf, 2)
    _asegurar_cuenta_4751(id_empresa)
    lineas = [{"codigo_cuenta": M.cuenta("nomina_sueldos", id_empresa=id_empresa), "debe": dev,
               "descripcion": "Sueldos y salarios"}]
    if ss_e:
        lineas.append({"codigo_cuenta": M.cuenta("nomina_ss_empresa", id_empresa=id_empresa),
                       "debe": ss_e, "descripcion": "SS a cargo de la empresa"})
    if round(ss_e + ss_t, 2):
        lineas.append({"codigo_cuenta": M.cuenta("nomina_ss_acreedora", id_empresa=id_empresa),
                       "haber": round(ss_e + ss_t, 2), "descripcion": "Organismos SS acreedores"})
    if irpf:
        lineas.append({"codigo_cuenta": M.cuenta("nomina_irpf", id_empresa=id_empresa),
                       "haber": irpf, "descripcion": "HP acreedora por IRPF"})
    if liquido:
        lineas.append({"codigo_cuenta": M.cuenta("nomina_liquido", id_empresa=id_empresa),
                       "haber": liquido, "descripcion": "Remuneraciones pendientes de pago"})
    r = A.crear_asiento(ev["fecha_evento"], lineas, concepto=f"Nómina {ev['ref']}",
                        origen="nomina", ref_origen=f"nomina:{ev['ref']}", id_empresa=id_empresa, idempotente=True)
    return r["id"] if r else None


# ── Gastos directos (suministros, servicios, dietas…) — entrada de un clic ────────
def _asegurar_cuenta_gasto(codigo, id_empresa):
    """Crea la cuenta de gasto 62x si la empresa se activó antes de existir esta función.
    Idempotente: solo crea si falta."""
    try:
        if not K.obtener_cuenta(codigo, id_empresa):
            nombre = M.CUENTAS_GASTO.get(codigo, f"Gasto {codigo}")
            K.crear_cuenta(codigo, nombre, tipo="gasto", naturaleza="deudora", id_empresa=id_empresa)
    except Exception as e:
        logger.warning("_asegurar_cuenta_gasto(%s): %s", codigo, e)


def registrar_gasto(tipo, total, fecha=None, forma_pago="banco", concepto=None,
                    con_iva=True, tipo_iva=None, id_empresa=None, naturaleza_gasto=None) -> dict | None:
    """Registra un GASTO directo (luz, agua, gas, internet, dietas, transporte…) generando
    su asiento de partida doble contra la cuenta de gasto (62x) correspondiente al tipo.

        Debe   62X gasto        base
        Debe   472 IVA soportado cuota            (si con_iva)
        Haber  572/570/400       total            (banco / efectivo / a crédito)

    Instantáneo (aparece ya en Diario/Mayor/Balances/IVA). Devuelve el dict del asiento o None.

    `naturaleza_gasto` (opcional, migr. 0277): 'fijo_mensual'/'extraordinario' — etiqueta de qué
    sección de la pestaña "Libro de Gastos" procede el alta, para poder listar cada sección por
    separado (`listar_gastos(naturaleza_gasto=...)`). None (por defecto) para TODOS los demás
    llamadores (p. ej. la pestaña preexistente "Gastos"): comportamiento sin cambios.
    """
    id_empresa = _empresa(id_empresa)
    if not K.contabilidad_activa(id_empresa):
        return None
    total = round(float(total or 0), 2)
    if total <= 0:
        return None
    fecha = _fecha(fecha or _dt.date.today())
    cta_gasto = M.cuenta("gasto", str(tipo), id_empresa=id_empresa) or "629"
    _asegurar_cuenta_gasto(cta_gasto, id_empresa)

    # IVA (importe total IVA-incluido). tipo_iva forzado → desglose exacto; None → fiscalidad empresa.
    if not con_iva:
        base, cuota, tv = total, 0.0, 0.0
    elif tipo_iva is not None:
        tv = round(float(tipo_iva), 2)
        base = round(total / (1 + tv / 100.0), 2) if tv else total
        cuota = round(total - base, 2)
    else:
        base, cuota, tv = _desglose(total, id_empresa)

    # Contrapartida según forma de pago.
    fp = (forma_pago or "banco").strip().lower()
    if fp in ("credito", "crédito", "proveedor"):
        cta_contra = M.cuenta("proveedor", id_empresa=id_empresa)      # 400 (pendiente de pago)
    elif fp in ("efectivo", "caja"):
        cta_contra = M.cuenta_forma_pago("efectivo", id_empresa)       # 570
    else:                                                              # banco / tarjeta / transferencia
        cta_contra = M.cuenta_forma_pago("tarjeta", id_empresa)        # 572

    desc = (concepto or "").strip() or M.cuenta("gasto", str(tipo)) or "Gasto"
    lineas = [{"codigo_cuenta": cta_gasto, "debe": base, "descripcion": f"Gasto {tipo}"}]
    if cuota:
        lineas.append({"codigo_cuenta": M.cuenta("iva_sop", id_empresa=id_empresa), "debe": cuota,
                       "tipo_iva": tv, "descripcion": "IVA soportado"})
    lineas.append({"codigo_cuenta": cta_contra, "haber": total, "descripcion": "Pago del gasto"})

    ref = f"gasto:{tipo}:{fecha}:{total}:{_dt.datetime.now().strftime('%H%M%S%f')}"
    concepto_final = (concepto or "").strip() or f"Gasto {tipo} ({cta_gasto})"
    r = A.crear_asiento(fecha, lineas, concepto=concepto_final, origen="gasto",
                        ref_origen=ref, id_empresa=id_empresa)
    if r and naturaleza_gasto:
        # `crear_asiento` es compartida por media docena de llamadores (plantillas/cierre/
        # tesorería/importación/posting) — no se le añade un parámetro solo para este matiz de
        # "Gastos"; se persiste con un UPDATE puntual sobre el asiento recién creado (columna
        # aditiva y opcional, migr. 0277). `obtener_conexion()` va en autocommit.
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE contab_asientos SET naturaleza_gasto=%s WHERE id=%s AND id_empresa=%s",
                           (naturaleza_gasto, r["id"], id_empresa))
        except Exception as e:
            logger.warning("registrar_gasto: no se pudo persistir naturaleza_gasto(%s): %s",
                          r.get("id"), e)
    return r


def _asegurar_cuenta(codigo, nombre, tipo, naturaleza, id_empresa):
    """Crea una cuenta PGC si falta (idempotente)."""
    try:
        if not K.obtener_cuenta(codigo, id_empresa):
            K.crear_cuenta(codigo, nombre, tipo=tipo, naturaleza=naturaleza, id_empresa=id_empresa)
    except Exception as e:
        logger.warning("_asegurar_cuenta(%s): %s", codigo, e)


def registrar_consumo_materia_prima(ref, coste, fecha=None, concepto=None, id_empresa=None) -> dict | None:
    """Contabiliza el CONSUMO de materia prima (p. ej. obrador / producción) como GASTO de materias primas:

        Debe   601 Compras/consumo de materias primas   coste
        Haber  300 Existencias                            coste

    Sin IVA (movimiento interno de existencias → gasto). Idempotente por `ref`. Best-effort: devuelve el
    dict del asiento o None (nunca rompe la producción)."""
    id_empresa = _empresa(id_empresa)
    if not K.contabilidad_activa(id_empresa):
        return None
    coste = round(float(coste or 0), 2)
    if coste <= 0:
        return None
    fecha = _fecha(fecha or _dt.date.today())
    cta_gasto = M.cuenta("consumo_mp", id_empresa=id_empresa) or "601"
    cta_exist = M.cuenta("existencias", id_empresa=id_empresa) or "300"
    _asegurar_cuenta(cta_gasto, "Compras de materias primas", "gasto", "deudora", id_empresa)
    _asegurar_cuenta(cta_exist, "Existencias", "activo", "deudora", id_empresa)
    lineas = [{"codigo_cuenta": cta_gasto, "debe": coste, "descripcion": "Consumo de materia prima"},
              {"codigo_cuenta": cta_exist, "haber": coste, "descripcion": "Salida de existencias"}]
    return A.crear_asiento(fecha, lineas, concepto=(concepto or f"Consumo materia prima {ref}"),
                           origen="consumo_mp", ref_origen=f"consumo_mp:{ref}", id_empresa=id_empresa,
                           idempotente=True)


def anular_gasto(id_asiento, usuario=None, id_empresa=None) -> dict | None:
    """Anula un gasto por CONTRAASIENTO (no borra el original). Reutiliza asientos.anular."""
    return A.anular(id_asiento, usuario=usuario, id_empresa=_empresa(id_empresa))


def listar_gastos(anio=None, id_empresa=None, naturaleza_gasto=None) -> list:
    """Asientos de gasto directo (origen='gasto') del ejercicio, más recientes primero.

    OJO: esto son SOLO las altas manuales de un clic (pestaña "Gastos"). NO usar esta
    función para el Libro de Gastos — ahí falta el grueso del gasto real (facturas de
    proveedor). Usar `listar_gastos_completo()` para eso (ver más abajo).

    `naturaleza_gasto` (opcional, migr. 0277): filtra por 'fijo_mensual'/'extraordinario'
    (las dos secciones nuevas de "Libro de Gastos"). None (por defecto) devuelve TODO el gasto
    manual tal cual hoy — comportamiento sin cambios para la pestaña "Gastos" preexistente."""
    id_empresa = _empresa(id_empresa)
    filas = [a for a in A.listar_diario(id_empresa=id_empresa, anio=anio) if a.get("origen") == "gasto"]
    if naturaleza_gasto is not None:
        filas = [a for a in filas if a.get("naturaleza_gasto") == naturaleza_gasto]
    filas.sort(key=lambda a: (a.get("fecha") or "", a.get("numero") or 0), reverse=True)
    return filas


def listar_gastos_completo(anio=None, id_empresa=None) -> list:
    """Libro de Gastos COMPLETO (FASE B): une los asientos de gasto manual (`listar_gastos`,
    altas de un clic desde la pestaña "Gastos") CON las facturas de compra REALES
    (`compras_facturas`) — antes el Libro de Gastos solo mostraba las primeras y nunca las
    segundas, dejando fuera la parte más importante del gasto real de la empresa.

    Cada fila queda etiquetada por `origen` ('manual' o 'compra') para que no haya
    confusión sobre su procedencia. Esta función es EXCLUSIVA para vistas/informes que
    necesiten el gasto completo (p. ej. el render del Libro de Gastos); NO sustituye a
    `listar_gastos()`, que sigue alimentando tal cual la pestaña "Gastos" (donde se anula
    por asiento, algo que no tiene sentido para una factura de compra)."""
    id_empresa = _empresa(id_empresa)
    manuales = [dict(a, origen="manual",
                     importe=round(float(a.get("total_debe") or 0), 2))
                for a in listar_gastos(anio=anio, id_empresa=id_empresa)]
    compras = []
    try:
        filtros, params = ["f.id_empresa=%s"], [id_empresa]
        if anio:
            filtros.append("YEAR(f.fecha_factura)=%s"); params.append(int(anio))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT f.id_factura AS numero, f.fecha_factura AS fecha, "
                "CONCAT('Factura proveedor ', COALESCE(p.razon_social,'(sin proveedor)'), "
                "' nº ', COALESCE(f.numero_factura,'')) AS concepto, "
                "f.total AS importe, f.estado AS estado "
                "FROM compras_facturas f LEFT JOIN proveedores p ON p.id_proveedor=f.id_proveedor "
                "WHERE " + " AND ".join(filtros) + " ORDER BY f.fecha_factura DESC",
                tuple(params))
            compras = [dict(r, origen="compra", importe=round(float(r.get("importe") or 0), 2))
                       for r in _filas_a_dicts(cur, cur.fetchall())]
    except Exception as e:
        logger.error("listar_gastos_completo/compras: %s", e)
    todo = manuales + compras
    todo.sort(key=lambda g: (str(g.get("fecha") or ""), g.get("numero") or 0), reverse=True)
    return todo
