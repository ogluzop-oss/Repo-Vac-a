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


def _audit(usuario, accion, detalles):
    """Traza en auditoria_logs (best-effort; nunca rompe la operación)."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria(usuario or "sistema", accion, "cuentas_bancarias", detalles)
    except Exception as e:
        logger.debug("audit %s: %s", accion, e)
