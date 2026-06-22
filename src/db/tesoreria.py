"""
Tesorería — capa de persistencia (rama financiera).

FASE 1: cuentas bancarias (CRUD multiempresa/multitienda, IBAN cifrado en reposo con el
mismo patrón que pasarela_config, validación IBAN/BIC). Las fases siguientes (movimientos,
vencimientos, pagos a proveedor, conciliación, SEPA) amplían este módulo de forma aditiva.

Ver [[project_prod_endurecimiento]] (M1 contable, auditoría) y [[project_fiscal_c3]] (XML).
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion
from src.utils import iban as _iban

logger = logging.getLogger("tesoreria_db")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fila(cur, row):
    return row if isinstance(row, dict) else dict(zip([d[0] for d in cur.description], row))


def _descifrar_iban(valor):
    from src.utils import cripto
    return cripto.descifrar_seguro(valor) or (valor or "")


# ─────────────────────────────── Cuentas bancarias ───────────────────────────────
class ErrorCuentaBancaria(ValueError):
    """IBAN/BIC inválidos u otros datos de cuenta incorrectos."""


def crear_cuenta(nombre_cuenta, iban, *, titular=None, bic=None, entidad=None,
                 sucursal=None, moneda="EUR", saldo_inicial=0, id_tienda=None,
                 observaciones=None, usuario=None, id_empresa=None) -> int | None:
    """Da de alta una cuenta bancaria. Valida IBAN (mód-97) y BIC (si se aporta).
    Cifra el IBAN en reposo y guarda una máscara para la UI. Devuelve el id o lanza
    ErrorCuentaBancaria si los datos bancarios no son válidos."""
    id_empresa = _emp(id_empresa)
    if not nombre_cuenta:
        raise ErrorCuentaBancaria("nombre_cuenta requerido")
    iban_norm = _iban.normalizar_iban(iban)
    if not _iban.validar_iban(iban_norm):
        raise ErrorCuentaBancaria(f"IBAN inválido: {iban}")
    if bic and not _iban.validar_bic(bic):
        raise ErrorCuentaBancaria(f"BIC inválido: {bic}")
    from src.utils import cripto
    iban_cif = cripto.cifrar(iban_norm) if iban_norm else iban_norm
    mascara = _iban.mascara_iban(iban_norm)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cuentas_bancarias (id_empresa, id_tienda, nombre_cuenta, titular, "
                "iban, iban_mascara, bic, entidad, sucursal, moneda, saldo_inicial, observaciones) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_tienda, nombre_cuenta, titular, iban_cif, mascara,
                 (bic or "").upper() or None, entidad, sucursal, moneda,
                 round(float(saldo_inicial or 0), 2), observaciones))
            cid = cur.lastrowid
            conn.commit()
        _audit(usuario, "alta_cuenta_bancaria", f"cuenta={cid} {mascara}")
        return cid
    except ErrorCuentaBancaria:
        raise
    except Exception as e:
        logger.error("crear_cuenta: %s", e)
        return None


def actualizar_cuenta(id_cuenta, *, usuario=None, id_empresa=None, **campos) -> bool:
    """Actualiza campos de una cuenta (solo los indicados). Si llega `iban`, lo revalida,
    recifra y regenera la máscara. Campos permitidos: nombre_cuenta, titular, iban, bic,
    entidad, sucursal, moneda, saldo_inicial, activa, observaciones, id_tienda."""
    id_empresa = _emp(id_empresa)
    permitidos = {"nombre_cuenta", "titular", "bic", "entidad", "sucursal", "moneda",
                  "saldo_inicial", "activa", "observaciones", "id_tienda"}
    sets, vals = [], []
    if "iban" in campos and campos["iban"] is not None:
        iban_norm = _iban.normalizar_iban(campos.pop("iban"))
        if not _iban.validar_iban(iban_norm):
            raise ErrorCuentaBancaria(f"IBAN inválido")
        from src.utils import cripto
        sets += ["iban=%s", "iban_mascara=%s"]
        vals += [cripto.cifrar(iban_norm), _iban.mascara_iban(iban_norm)]
    if campos.get("bic") and not _iban.validar_bic(campos["bic"]):
        raise ErrorCuentaBancaria("BIC inválido")
    for k, v in campos.items():
        if k in permitidos:
            sets.append(f"{k}=%s")
            vals.append(round(float(v), 2) if k == "saldo_inicial" else v)
    if not sets:
        return False
    vals += [id_cuenta, id_empresa]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE cuentas_bancarias SET {', '.join(sets)} "
                        "WHERE id=%s AND id_empresa=%s", vals)
            ok = cur.rowcount >= 0
            conn.commit()
        _audit(usuario, "modif_cuenta_bancaria", f"cuenta={id_cuenta}")
        return ok
    except ErrorCuentaBancaria:
        raise
    except Exception as e:
        logger.error("actualizar_cuenta: %s", e)
        return False


def desactivar_cuenta(id_cuenta, usuario=None, id_empresa=None) -> bool:
    """Baja lógica (activa=0). No borra para preservar la trazabilidad de movimientos."""
    return actualizar_cuenta(id_cuenta, activa=0, usuario=usuario, id_empresa=id_empresa)


def obtener_cuenta(id_cuenta, *, descifrar=False, id_empresa=None) -> dict | None:
    """Devuelve una cuenta. Por defecto NO descifra el IBAN (usa la máscara);
    con descifrar=True incluye `iban` en claro (para SEPA/conciliación)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cuentas_bancarias WHERE id=%s AND id_empresa=%s",
                        (id_cuenta, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            d = _fila(cur, r)
            d["iban"] = _descifrar_iban(d["iban"]) if descifrar else d.get("iban_mascara")
            return d
    except Exception as e:
        logger.error("obtener_cuenta: %s", e)
        return None


def listar_cuentas(*, solo_activas=True, id_tienda=None, id_empresa=None) -> list:
    """Lista cuentas de la empresa (IBAN como máscara). Filtra por tienda si se indica."""
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM cuentas_bancarias WHERE id_empresa=%s"
    p = [id_empresa]
    if solo_activas:
        q += " AND activa=1"
    if id_tienda is not None:
        q += " AND id_tienda=%s"
        p.append(id_tienda)
    q += " ORDER BY activa DESC, nombre_cuenta"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            out = []
            for r in cur.fetchall():
                d = _fila(cur, r)
                d["iban"] = d.get("iban_mascara")   # nunca expone el IBAN en claro en listados
                out.append(d)
            return out
    except Exception as e:
        logger.error("listar_cuentas: %s", e)
        return []


def _audit(usuario, accion, detalles, tabla="cuentas_bancarias"):
    """Traza en auditoria_logs (best-effort; nunca rompe la operación)."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria(usuario or "sistema", accion, tabla, detalles)
    except Exception as e:
        logger.debug("audit %s: %s", accion, e)


# ─────────────────────────────── Movimientos de tesorería (FASE 2) ───────────────────────────────
TIPOS_MOV = ("COBRO", "PAGO", "TRANSFERENCIA", "AJUSTE", "CONCILIACION",
             "NOMINA", "IMPUESTO", "COMISION")


def _hash_mov(prev, id_empresa, fecha, tipo, importe, id_documento):
    """Hash documental encadenado (SHA-256) sobre el hash previo de la empresa."""
    import hashlib
    base = f"{prev or ''}|{id_empresa}|{fecha}|{tipo}|{importe}|{id_documento or ''}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def registrar_movimiento(tipo, importe, *, id_cuenta=None, fecha=None, concepto=None,
                         referencia=None, origen="manual", id_documento=None,
                         usuario=None, idempotente=False, id_empresa=None) -> int | None:
    """Registra un movimiento en el libro de tesorería.

    `importe` es CON SIGNO (+ entrada / − salida). Calcula el saldo corrido de la cuenta
    (saldo_inicial + Σ importes) y un hash documental encadenado. Si `idempotente` y hay
    `id_documento`, no duplica un movimiento ya existente con el mismo (origen, tipo,
    id_documento) — patrón M1 (devuelve el id existente). Devuelve el id o None."""
    id_empresa = _emp(id_empresa)
    tipo = (tipo or "").upper()
    if tipo not in TIPOS_MOV:
        logger.warning("registrar_movimiento: tipo inválido %s", tipo)
        return None
    try:
        importe = round(float(importe), 2)
    except (TypeError, ValueError):
        return None
    f = fecha
    if f is None:
        import datetime as _dt
        f = _dt.date.today().strftime("%Y-%m-%d")
    elif hasattr(f, "strftime"):
        f = f.strftime("%Y-%m-%d")
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            if idempotente and id_documento is not None:
                cur.execute("SELECT id FROM movimientos_tesoreria WHERE id_empresa=%s AND "
                            "origen=%s AND tipo=%s AND id_documento=%s LIMIT 1",
                            (id_empresa, origen, tipo, str(id_documento)))
                ya = cur.fetchone()
                if ya:
                    return ya[0] if not isinstance(ya, dict) else list(ya.values())[0]
            # Saldo corrido de la cuenta (último saldo o saldo_inicial de la cuenta).
            base_saldo = 0.0
            if id_cuenta is not None:
                cur.execute("SELECT saldo_resultante FROM movimientos_tesoreria WHERE id_empresa=%s "
                            "AND id_cuenta=%s ORDER BY id DESC LIMIT 1", (id_empresa, id_cuenta))
                r = cur.fetchone()
                if r and (r[0] if not isinstance(r, dict) else list(r.values())[0]) is not None:
                    base_saldo = float(r[0] if not isinstance(r, dict) else list(r.values())[0])
                else:
                    cur.execute("SELECT saldo_inicial FROM cuentas_bancarias WHERE id=%s AND id_empresa=%s",
                                (id_cuenta, id_empresa))
                    rc = cur.fetchone()
                    if rc:
                        base_saldo = float(rc[0] if not isinstance(rc, dict) else list(rc.values())[0])
            saldo = round(base_saldo + importe, 2)
            # Hash encadenado por empresa.
            cur.execute("SELECT hash FROM movimientos_tesoreria WHERE id_empresa=%s "
                        "ORDER BY id DESC LIMIT 1", (id_empresa,))
            rp = cur.fetchone()
            prev = (rp[0] if rp and not isinstance(rp, dict) else rp.get("hash") if rp else None)
            h = _hash_mov(prev, id_empresa, f, tipo, importe, id_documento)
            cur.execute(
                "INSERT INTO movimientos_tesoreria (id_empresa, id_cuenta, fecha, tipo, concepto, "
                "importe, saldo_resultante, referencia, origen, id_documento, usuario, hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_cuenta, f, tipo, concepto, importe, saldo, referencia,
                 origen, (str(id_documento) if id_documento is not None else None), usuario, h))
            mid = cur.lastrowid
            conn.commit()
        _audit(usuario, "movimiento_tesoreria", f"id={mid} {tipo} {importe}",
               tabla="movimientos_tesoreria")
        # FASE 10 — asiento contable M1 (idempotente) para cobros/pagos. Best-effort.
        if tipo in ("COBRO", "PAGO"):
            try:
                from src.services.tesoreria import contabilidad as _TC
                _TC.contabilizar_movimiento({"id": mid, "tipo": tipo, "importe": importe,
                                             "id_cuenta": id_cuenta, "fecha": f,
                                             "concepto": concepto}, id_empresa=id_empresa)
            except Exception as e:
                logger.debug("contab movimiento: %s", e)
        return mid
    except Exception as e:
        # UNIQUE de idempotencia: si choca por carrera, recupera el existente.
        if idempotente and id_documento is not None:
            try:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute("SELECT id FROM movimientos_tesoreria WHERE id_empresa=%s AND "
                                "origen=%s AND tipo=%s AND id_documento=%s LIMIT 1",
                                (id_empresa, origen, tipo, str(id_documento)))
                    ya = cur.fetchone()
                    if ya:
                        return ya[0] if not isinstance(ya, dict) else list(ya.values())[0]
            except Exception:
                pass
        logger.error("registrar_movimiento: %s", e)
        return None


def listar_movimientos(*, id_cuenta=None, desde=None, hasta=None, tipo=None,
                       origen=None, id_empresa=None, limite=1000) -> list:
    """Movimientos de tesorería (más recientes primero) con filtros opcionales."""
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM movimientos_tesoreria WHERE id_empresa=%s"
    p = [id_empresa]
    if id_cuenta is not None:
        q += " AND id_cuenta=%s"; p.append(id_cuenta)
    if tipo:
        q += " AND tipo=%s"; p.append(tipo.upper())
    if origen:
        q += " AND origen=%s"; p.append(origen)
    if desde:
        q += " AND fecha>=%s"; p.append(desde)
    if hasta:
        q += " AND fecha<=%s"; p.append(hasta)
    q += " ORDER BY fecha DESC, id DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_movimientos: %s", e)
        return []


def saldo_cuenta(id_cuenta, id_empresa=None) -> float:
    """Saldo real de una cuenta = saldo_inicial + Σ importes de sus movimientos."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(saldo_inicial,0) FROM cuentas_bancarias "
                        "WHERE id=%s AND id_empresa=%s", (id_cuenta, id_empresa))
            r = cur.fetchone()
            ini = float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0.0
            cur.execute("SELECT COALESCE(SUM(importe),0) FROM movimientos_tesoreria "
                        "WHERE id_empresa=%s AND id_cuenta=%s", (id_empresa, id_cuenta))
            r2 = cur.fetchone()
            mov = float((r2[0] if not isinstance(r2, dict) else list(r2.values())[0]) or 0)
            return round(ini + mov, 2)
    except Exception as e:
        logger.error("saldo_cuenta: %s", e)
        return 0.0


def transferencia(id_cuenta_origen, id_cuenta_destino, importe, *, fecha=None,
                  concepto=None, usuario=None, id_empresa=None) -> tuple:
    """Transferencia entre dos cuentas propias: genera dos movimientos TRANSFERENCIA
    (salida en origen, entrada en destino) enlazados por la misma referencia."""
    id_empresa = _emp(id_empresa)
    importe = abs(round(float(importe), 2))
    import uuid as _u
    ref = "TRF-" + _u.uuid4().hex[:10]
    c = (concepto or f"Transferencia {id_cuenta_origen}→{id_cuenta_destino}")
    m1 = registrar_movimiento("TRANSFERENCIA", -importe, id_cuenta=id_cuenta_origen, fecha=fecha,
                              concepto=c, referencia=ref, origen="transferencia",
                              id_documento=ref + ":out", usuario=usuario, id_empresa=id_empresa)
    m2 = registrar_movimiento("TRANSFERENCIA", importe, id_cuenta=id_cuenta_destino, fecha=fecha,
                              concepto=c, referencia=ref, origen="transferencia",
                              id_documento=ref + ":in", usuario=usuario, id_empresa=id_empresa)
    # FASE 10 — un único asiento por la transferencia (idempotente).
    try:
        from src.services.tesoreria import contabilidad as _TC
        _TC.contabilizar_transferencia(ref, fecha, importe, id_empresa=id_empresa)
    except Exception as e:
        logger.debug("contab transferencia: %s", e)
    return (m1, m2, ref)
