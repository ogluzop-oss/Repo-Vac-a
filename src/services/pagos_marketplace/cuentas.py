"""
Cuentas conectadas del PSP (modelo tokenizado) — F0 del Marketplace + Pagos.

Una fila por PARTE (empresa | proveedor | vendedor de la Lonja) en `psp_cuentas_conectadas`. Se guarda el
**token opaco** de la cuenta del PSP (`account_id`) y metadatos visuales/de estado (banco, últimos 4,
divisa, estado KYB, payouts/charges habilitados). **Nunca** el IBAN completo.

Flujo (Gemini): la parte pulsa "Conectar cobros (KYB)" → `crear_onboarding` provisiona la cuenta conectada
en el PSP y devuelve una `onboarding_url` hospedada; la parte completa allí sus datos y el PSB valida
(KYB/antiblanqueo); el PSP notifica por webhook (`account.updated`) y `sincronizar_estado` actualiza banco,
últimos 4 y estado. La UI muestra "Banco ···1332 · verificado", pero toda orden de cobro/liquidación se
ejecuta llamando a la API del PSP con el `account_id`.

DEGRADABLE: sin adaptador de marketplace configurado (F1) ni credenciales, provisiona una cuenta en modo
SIMULADO para desarrollo/pruebas — nunca finge un estado "verified" real (queda 'pending').
"""

import logging

logger = logging.getLogger("pagos_marketplace.cuentas")

TIPOS_PARTE = ("empresa", "proveedor", "vendedor")
ESTADOS = ("pending", "verified", "restricted", "rejected")


def _emp(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return id_empresa or EMPRESA_DEFAULT_ID


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def _norm_parte(tipo_parte) -> str:
    t = (tipo_parte or "empresa").strip().lower()
    return t if t in TIPOS_PARTE else "empresa"


# ── Persistencia (upsert / lectura) ──────────────────────────────────────────
def registrar_token(tipo_parte, id_parte, account_id, *, psp="stripe", status="pending",
                    banco=None, ultimos4=None, divisa="EUR", payouts_enabled=False,
                    charges_enabled=False, onboarding_url=None, id_empresa=None) -> dict:
    """Upsert de la cuenta conectada de una parte. Idempotente por (empresa, tipo_parte, id_parte, psp)."""
    emp = _emp(id_empresa)
    tp = _norm_parte(tipo_parte)
    st = status if status in ESTADOS else "pending"
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO psp_cuentas_conectadas "
                "(id_empresa, tipo_parte, id_parte, psp, account_id, status, payouts_enabled, "
                " charges_enabled, banco, ultimos4, divisa, onboarding_url) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE account_id=VALUES(account_id), status=VALUES(status), "
                " payouts_enabled=VALUES(payouts_enabled), charges_enabled=VALUES(charges_enabled), "
                " banco=COALESCE(VALUES(banco), banco), ultimos4=COALESCE(VALUES(ultimos4), ultimos4), "
                " divisa=VALUES(divisa), onboarding_url=COALESCE(VALUES(onboarding_url), onboarding_url)",
                (emp, tp, int(id_parte or 0), psp, account_id, st, int(bool(payouts_enabled)),
                 int(bool(charges_enabled)), banco, ultimos4, (divisa or "EUR").upper(), onboarding_url))
            c.commit()
        return {"ok": True, "account_id": account_id, "status": st}
    except Exception as e:
        logger.error("registrar_token: %s", e)
        return {"ok": False, "error": str(e)[:160]}


def resumen(tipo_parte, id_parte, id_empresa=None) -> dict | None:
    """Metadatos para la UI (banco, últimos 4, estado, payouts) o None si la parte no ha conectado cobros.
    NUNCA devuelve datos bancarios sensibles: solo el token y su máscara."""
    emp = _emp(id_empresa)
    tp = _norm_parte(tipo_parte)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT account_id, status, payouts_enabled, charges_enabled, banco, ultimos4, divisa, "
                " onboarding_url, actualizado FROM psp_cuentas_conectadas "
                "WHERE id_empresa=%s AND tipo_parte=%s AND id_parte=%s ORDER BY id DESC LIMIT 1",
                (emp, tp, int(id_parte or 0)))
            r = _filas(cur)
        if not r:
            return None
        d = r[0]
        d["payouts_enabled"] = bool(d.get("payouts_enabled"))
        d["charges_enabled"] = bool(d.get("charges_enabled"))
        # Etiqueta lista para la UI: "CaixaBank ···1332" (sin exponer IBAN).
        banco = d.get("banco") or "Cuenta bancaria"
        d["etiqueta"] = f"{banco} ···{d['ultimos4']}" if d.get("ultimos4") else banco
        return d
    except Exception as e:
        logger.error("resumen: %s", e)
        return None


def cuenta_por_account_id(account_id) -> dict | None:
    """Localiza la fila por el token del PSP (lo usa el webhook `account.updated`)."""
    if not account_id:
        return None
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM psp_cuentas_conectadas WHERE account_id=%s LIMIT 1", (account_id,))
            r = _filas(cur)
        return r[0] if r else None
    except Exception as e:
        logger.error("cuenta_por_account_id: %s", e)
        return None


def sincronizar_estado(account_id, *, status=None, payouts_enabled=None, charges_enabled=None,
                       banco=None, ultimos4=None) -> bool:
    """Actualiza estado/metadatos desde el PSP (webhook `account.updated`). Solo toca lo que llega."""
    if not account_id:
        return False
    sets, params = [], []
    if status is not None:
        sets.append("status=%s"); params.append(status if status in ESTADOS else "pending")
    if payouts_enabled is not None:
        sets.append("payouts_enabled=%s"); params.append(int(bool(payouts_enabled)))
    if charges_enabled is not None:
        sets.append("charges_enabled=%s"); params.append(int(bool(charges_enabled)))
    if banco is not None:
        sets.append("banco=%s"); params.append(banco)
    if ultimos4 is not None:
        sets.append("ultimos4=%s"); params.append(ultimos4)
    if not sets:
        return False
    params.append(account_id)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE psp_cuentas_conectadas SET " + ", ".join(sets)
                        + " WHERE account_id=%s", tuple(params))
            ok = cur.rowcount >= 0
            c.commit()
        return ok
    except Exception as e:
        logger.error("sincronizar_estado: %s", e)
        return False


# ── Onboarding (delegado al PSP; degradable a simulado) ───────────────────────
def crear_onboarding(tipo_parte, id_parte, *, divisa="EUR", id_empresa=None, email=None) -> dict:
    """Provisiona la cuenta conectada en el PSP y devuelve el enlace de onboarding hospedado (KYB).

    Reutiliza el adaptador de marketplace de `services.tpv.pagos` (F1) si está disponible y configurado;
    en su defecto degrada a un provisión SIMULADO (cuenta 'pending' con account_id de prueba), útil para
    desarrollo sin credenciales. Nunca marca 'verified' sin acuse real del PSP."""
    emp = _emp(id_empresa)
    tp = _norm_parte(tipo_parte)
    div = (divisa or "EUR").upper()
    from src.services.pagos_marketplace import psp
    prov = psp.adaptador(emp)
    try:
        res = prov.crear_cuenta_conectada(tipo_parte=tp, id_parte=id_parte, divisa=div, email=email,
                                          id_empresa=emp)
    except Exception as e:
        logger.warning("crear_onboarding (adaptador): %s", e)
        res = {"ok": False, "mensaje": str(e)}
    if not res.get("ok"):
        return {"ok": False, "error": res.get("mensaje", "No se pudo crear la cuenta conectada.")}
    registrar_token(tp, id_parte, res.get("account_id"), psp=res.get("psp", "stripe"),
                    status=res.get("status", "pending"), divisa=div,
                    onboarding_url=res.get("onboarding_url"), id_empresa=emp)
    return {"ok": True, "account_id": res.get("account_id"), "onboarding_url": res.get("onboarding_url"),
            "status": res.get("status", "pending"), "modo": prov.modo()}


def refrescar_estado(tipo_parte, id_parte, id_empresa=None) -> dict:
    """Consulta el estado KYB actual en el PSP y lo sincroniza (para un botón 'Actualizar' o tras el KYB).
    Devuelve el resumen actualizado o {ok:False}."""
    emp = _emp(id_empresa)
    res = resumen(tipo_parte, id_parte, emp)
    if not res or not res.get("account_id"):
        return {"ok": False, "error": "La parte no ha conectado cobros todavía."}
    from src.services.pagos_marketplace import psp
    est = psp.adaptador(emp).estado_cuenta(res["account_id"])
    if est.get("ok"):
        sincronizar_estado(res["account_id"], status=est.get("status"),
                           payouts_enabled=est.get("payouts_enabled"),
                           charges_enabled=est.get("charges_enabled"),
                           banco=est.get("banco"), ultimos4=est.get("ultimos4"))
    return {"ok": bool(est.get("ok")), "resumen": resumen(tipo_parte, id_parte, emp)}
