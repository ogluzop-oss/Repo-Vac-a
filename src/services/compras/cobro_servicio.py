"""
Cuentas bancarias (proveedores/vendedores) + cobro del servicio Smart Manager.

- Cuentas de EMPRESAS: ya existen en `cuentas_bancarias` (migr 0045) — se reutilizan (no se duplican).
- Cuentas de PROVEEDORES/VENDEDORES: IBAN cifrado en reposo (`utils.cripto`) + máscara para la UI
  (`utils.iban`), igual que las de empresa.
- Cobro del servicio: a la EMPRESA se le cobra la app; al PROVEEDOR, el portal desde el que sube sus
  productos; y opcionalmente una comisión por venta del mercado. Todo en `servicio_cobros` (idempotente
  por empresa+parte+proveedor+concepto+periodo).
"""

import datetime as _dt
import logging

logger = logging.getLogger("compras.cobro_servicio")

CONCEPTOS = ("app", "portal", "comision")
ESTADOS = ("pendiente", "cobrado", "fallido")


def _emp(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        return id_empresa


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def _periodo(periodo=None) -> str:
    return periodo or _dt.date.today().strftime("%Y-%m")


def _cifrar_iban(iban):
    """Valida, normaliza, cifra el IBAN y devuelve (cifrado, mascara). Lanza si es inválido."""
    from src.utils import cripto, iban as _iban
    norm = _iban.normalizar_iban(iban)
    if not _iban.validar_iban(norm):
        raise ValueError(f"IBAN inválido: {iban}")
    return cripto.cifrar(norm), _iban.mascara_iban(norm)


# ── Cuentas bancarias de proveedores / vendedores ────────────────────────────
# DEPRECADO (Marketplace + Pagos, F0): la captura directa de IBAN — aunque cifrado — NO es el modelo
# correcto para un marketplace B2B con fondos de terceros (implica custodia y licencia de entidad de pago).
# La vía correcta es el modelo TOKENIZADO del PSP regulado: `services.pagos_marketplace.cuentas`
# (`crear_onboarding` → onboarding KYB hospedado del PSP; se guarda solo el token opaco + metadatos).
# Estas funciones se conservan un ciclo por compatibilidad; NO deben cablearse a UI nueva.
import warnings as _warnings


def set_cuenta_proveedor(id_proveedor, iban, *, titular=None, id_empresa=None) -> dict:
    _warnings.warn("set_cuenta_proveedor está deprecado; usa services.pagos_marketplace.cuentas "
                   "(modelo tokenizado del PSP).", DeprecationWarning, stacklevel=2)
    emp = _emp(id_empresa)
    try:
        cif, mask = _cifrar_iban(iban)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE proveedores SET iban_cifrado=%s, iban_mascara=%s, titular_cuenta=%s "
                        "WHERE id_proveedor=%s AND id_empresa=%s", (cif, mask, titular, id_proveedor, emp))
            c.commit()
        return {"ok": True, "iban_mascara": mask}
    except Exception as e:
        logger.error("set_cuenta_proveedor: %s", e)
        return {"ok": False, "error": str(e)[:120]}


def cuenta_proveedor(id_proveedor, id_empresa=None) -> dict | None:
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT iban_mascara, titular_cuenta FROM proveedores "
                        "WHERE id_proveedor=%s AND id_empresa=%s", (id_proveedor, emp))
            r = _filas(cur)
        return r[0] if r else None
    except Exception as e:
        logger.error("cuenta_proveedor: %s", e)
        return None


def set_cuenta_vendedor(id_vendedor, iban) -> dict:
    _warnings.warn("set_cuenta_vendedor está deprecado; usa services.pagos_marketplace.cuentas "
                   "(modelo tokenizado del PSP).", DeprecationWarning, stacklevel=2)
    try:
        cif, mask = _cifrar_iban(iban)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE lonja_vendedores SET iban_cifrado=%s, iban_mascara=%s WHERE id=%s",
                        (cif, mask, id_vendedor))
            c.commit()
        return {"ok": True, "iban_mascara": mask}
    except Exception as e:
        logger.error("set_cuenta_vendedor: %s", e)
        return {"ok": False, "error": str(e)[:120]}


# ── Cobro del servicio ───────────────────────────────────────────────────────
def _cobrar(id_empresa, parte, concepto, importe, *, id_proveedor=None, periodo=None, divisa="EUR",
            iban_mascara=None) -> int | None:
    emp = _emp(id_empresa)
    per = _periodo(periodo)
    con = concepto if concepto in CONCEPTOS else "app"
    # id_proveedor=0 para cobros de empresa (evita que MySQL trate NULL como distinto en el UNIQUE →
    # así la idempotencia por periodo funciona también para la app).
    idp = int(id_proveedor) if id_proveedor else 0
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("INSERT INTO servicio_cobros (id_empresa, parte, id_proveedor, concepto, importe, "
                        "divisa, periodo, iban_mascara) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE importe=VALUES(importe), divisa=VALUES(divisa), "
                        "iban_mascara=VALUES(iban_mascara)",
                        (emp, parte, idp, con, float(importe or 0), divisa, per, iban_mascara))
            cur.execute("SELECT id FROM servicio_cobros WHERE id_empresa=%s AND parte=%s "
                        "AND id_proveedor=%s AND concepto=%s AND periodo<=>%s",
                        (emp, parte, idp, con, per))
            r = _filas(cur)
            c.commit()
        return r[0]["id"] if r else None
    except Exception as e:
        logger.error("_cobrar: %s", e)
        return None


def cobrar_app(id_empresa, importe, *, periodo=None, divisa="EUR") -> int | None:
    """Cobra a la EMPRESA el uso de la app (idempotente por periodo)."""
    return _cobrar(id_empresa, "empresa", "app", importe, periodo=periodo, divisa=divisa)


def cobrar_portal(id_proveedor, importe, *, id_empresa=None, periodo=None, divisa="EUR") -> int | None:
    """Cobra al PROVEEDOR el uso del portal desde el que sube sus productos (idempotente por periodo)."""
    mask = (cuenta_proveedor(id_proveedor, id_empresa) or {}).get("iban_mascara")
    return _cobrar(id_empresa, "proveedor", "portal", importe, id_proveedor=id_proveedor,
                   periodo=periodo, divisa=divisa, iban_mascara=mask)


def listar_cobros(id_empresa=None, *, estado=None, parte=None) -> list:
    emp = _emp(id_empresa)
    cond, params = ["id_empresa=%s"], [emp]
    if estado:
        cond.append("estado=%s"); params.append(estado)
    if parte:
        cond.append("parte=%s"); params.append(parte)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, parte, id_proveedor, concepto, importe, divisa, periodo, estado, "
                        "iban_mascara, creado_en FROM servicio_cobros WHERE " + " AND ".join(cond)
                        + " ORDER BY creado_en DESC", tuple(params))
            return _filas(cur)
    except Exception as e:
        logger.error("listar_cobros: %s", e)
        return []


def marcar_cobrado(id_cobro, id_empresa=None) -> bool:
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE servicio_cobros SET estado='cobrado', cobrado_en=NOW() "
                        "WHERE id=%s AND id_empresa=%s", (id_cobro, emp))
            ok = cur.rowcount > 0
            c.commit()
        return ok
    except Exception as e:
        logger.error("marcar_cobrado: %s", e)
        return False


def total_pendiente(id_empresa=None) -> float:
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(importe),0) AS t FROM servicio_cobros "
                        "WHERE id_empresa=%s AND estado='pendiente'", (emp,))
            r = _filas(cur)
        return float(r[0]["t"]) if r else 0.0
    except Exception as e:
        logger.error("total_pendiente: %s", e)
        return 0.0
