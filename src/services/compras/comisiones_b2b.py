"""
Motor de comisiones de plataforma sobre pedidos B2B (petición explícita, 2026-11-16; sincronización
comercial con la web oficial añadida el mismo día; exención por el lado del PROVEEDOR añadida
2026-11-21; corregido el MISMO día para que las dos exenciones sean INDEPENDIENTES entre sí —ver
más abajo—, tras confirmar con el usuario que la regla "O" implementada antes era incorrecta).

Regla vigente, confirmada explícitamente con el usuario (2026-11-21): la exención del 2.5% es
TOTALMENTE INDEPENDIENTE para cada parte — que la empresa compradora tenga una suscripción activa a
Smart Manager NUNCA exime al proveedor, y viceversa. Cada lado paga su propio 2.5% salvo que ÉL
MISMO (no la otra parte) tenga una suscripción activa a la app de escritorio, en CUALQUIER plan
(Basic/Plus/Pro) — se tratan como "activa" los estados 'activa' Y 'prueba' (mismo criterio ya usado
en `licensing.modulo_habilitado`; el periodo de prueba también exime). Por cada lado, esto se
resuelve de DOS formas posibles:
  - Directamente por `id_empresa`/`id_suministrador` LOCAL, si esa parte entró al portal DESDE
    el escritorio de Smart Manager (`crear_sesion`, mismo id real — `licensing.estado_operativo`).
  - Si esa parte se registró PÚBLICAMENTE en su portal (sin relación con ninguna licencia local),
    por su EMAIL de acceso, si coincide con un cliente de pago activo del alta SaaS de la web
    oficial — ver `services.saas.suscripcion_lookup`. Se resuelve vía una caché local con TTL
    (`empresas.comision_exenta_web*` migr. 0343 para la empresa compradora;
    `suministradores.comision_exenta_proveedor*` migr. 0351 para el proveedor): cada empresa
    SaaS vive en su PROPIA base de datos aislada (`services.provisioning.
    aprovisionar_tenant_nuevo`), así que resolverlo en vivo en cada pedido implicaría conectar a
    la base de otro tenant en cada transacción.

Por eso la API pública de este módulo está deliberadamente SEPARADA por lado (`porcentaje_comprador`/
`porcentaje_proveedor`, `calcular_comprador`/`calcular_proveedor`, `desglose_comprador`/
`desglose_proveedor`): cada portal (Proveedor / Empresa B2B) debe consultar y mostrar EXCLUSIVAMENTE
el cálculo de su propio lado, sin referenciar nunca el estado de suscripción de la otra parte (ni en
el cálculo ni en el texto). `recargos_transaccion()` es la única función que combina ambos lados — de
uso INTERNO, reservado a `b2b_escrow.py` para calcular el cobro real al comprador y el reparto real
del cargo de aplicación en Stripe Connect; ningún portal debe llamarla directamente.

OJO (semántica invertida de `licensing.py`, ver su propio docstring): `licencia_activa()` devuelve
`None` para una empresa SIN ninguna fila en `empresa_licencia`, y el resto del código LEGACY trata
ese `None` como "sin restricción" (permisivo, pensado para instalaciones de escritorio preexistentes
sin SaaS). Aquí es justo lo contrario: "sin licencia" es la señal de que SÍ hay que cobrar el 2.5% —
por eso se comprueba explícitamente el estado devuelto por `estado_operativo()`, nunca se asume el
comportamiento permisivo por defecto de esa función.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger("compras.comisiones_b2b")

PCT_EXENTA = 0.0                    # esa parte, por sí sola, tiene suscripción activa/en prueba
# Comisión por transacción retirada por completo (petición explícita, 2026-11-27): "eliminamos
# por completo la comisión porcentual... independientemente de si el usuario tiene suscripción o
# no". Los portales pasan a ser un embudo de captación hacia el ERP (ver `services/portal_plan.py`
# para el plan Freemium/de pago de los portales, que sustituye a la comisión como palanca
# comercial) — nunca una fuente de fricción/comisión en sí mismos. Se mantiene la función/firma
# (`porcentaje_comprador`/`porcentaje_proveedor`, `_empresa_exenta`/`_proveedor_exento`) y el resto
# del motor intactos a propósito: con esta constante en 0.0, TODO el cálculo aguas abajo
# (`calcular_*`, `desglose_*`, `recargos_transaccion`, `b2b_escrow.py`) sigue funcionando igual,
# simplemente siempre da 0 — cero lógica duplicada, cero rama especial "sin comisión" nueva.
PCT_SIN_SUSCRIPCION = 0.0           # antes 2.5 — retirada, ver nota arriba

_ESTADOS_EXENTOS = ("activa", "prueba")
TTL_CACHE_EXENCION_HORAS = 12       # revalidación periódica de la sincronización con la web oficial


def _email_login_b2b(id_empresa):
    """Email de acceso al Portal B2B de esta empresa — solo existe para altas PÚBLICAS (ver
    `b2b_sesion_empresa.registrar_publico`); `None` si la empresa entró desde el escritorio (esa ya
    se resuelve por `id_empresa` local, sin necesidad de este puente)."""
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT email_login FROM b2b_empresas_credenciales WHERE id_empresa=%s",
                       (id_empresa,))
            row = cur.fetchone()
            if not row:
                return None
            return row[0] if not isinstance(row, dict) else row["email_login"]
    except Exception as e:
        logger.error("_email_login_b2b(%s): %s", id_empresa, e)
        return None


def _email_login_proveedor(id_suministrador):
    """Email de acceso al Portal Proveedor de este suministrador (`suministradores.email_login`,
    siempre presente — a diferencia de la empresa compradora, un proveedor SIEMPRE se registra con
    email+contraseña propios, nunca "entra desde el escritorio"; ver `portal_proveedor.py`)."""
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT email_login FROM suministradores WHERE id=%s", (id_suministrador,))
            row = cur.fetchone()
            if not row:
                return None
            return row[0] if not isinstance(row, dict) else row["email_login"]
    except Exception as e:
        logger.error("_email_login_proveedor(%s): %s", id_suministrador, e)
        return None


def _exencion_cacheada_generica(*, tabla, col_id, id_valor, col_exenta, col_check, email) -> bool:
    """Caché local con TTL de "¿este email tiene una suscripción activa a Smart Manager vía la web
    oficial?" (migr. 0343 para `empresas`, migr. 0351 para `suministradores` — misma forma exacta
    de caché, solo cambia la tabla/columnas) — ver docstring de cabecera. Revalida en vivo
    (`suscripcion_lookup`) si la caché está vacía o caducada; nunca lanza, degrada a `False` (no
    exime) ante cualquier fallo de resolución."""
    from src.db.conexion import obtener_conexion
    if not email:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {col_exenta}, {col_check} FROM {tabla} WHERE {col_id}=%s",
                       (id_valor,))
            row = cur.fetchone()
            fila = (row if isinstance(row, dict) else
                   dict(zip([d[0] for d in cur.description], row))) if row else None
    except Exception as e:
        logger.error("_exencion_cacheada_generica(%s.%s=%s) lectura: %s", tabla, col_id, id_valor, e)
        return False
    check_en = fila.get(col_check) if fila else None
    fresca = check_en and (datetime.now() - check_en) < timedelta(hours=TTL_CACHE_EXENCION_HORAS)
    if fresca:
        return bool(fila[col_exenta])
    from src.services.saas import suscripcion_lookup
    exenta = suscripcion_lookup.tiene_suscripcion_activa_por_email(email)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE {tabla} SET {col_exenta}=%s, {col_check}=NOW() WHERE {col_id}=%s",
                       (1 if exenta else 0, id_valor))
            conn.commit()
    except Exception as e:
        logger.error("_exencion_cacheada_generica(%s.%s=%s) escritura: %s", tabla, col_id, id_valor, e)
    return exenta


def _exencion_web_cacheada(id_empresa) -> bool:
    email = _email_login_b2b(id_empresa)
    if not email:
        return False
    return _exencion_cacheada_generica(
        tabla="empresas", col_id="id_empresa", id_valor=id_empresa,
        col_exenta="comision_exenta_web", col_check="comision_exenta_web_check", email=email)


def _exencion_proveedor_cacheada(id_suministrador) -> bool:
    email = _email_login_proveedor(id_suministrador)
    if not email:
        return False
    return _exencion_cacheada_generica(
        tabla="suministradores", col_id="id", id_valor=id_suministrador,
        col_exenta="comision_exenta_proveedor", col_check="comision_exenta_proveedor_check",
        email=email)


def _empresa_exenta(id_empresa) -> bool:
    """¿Está exenta la EMPRESA COMPRADORA (suscripción local activa, o vía sincronización web)?"""
    if not id_empresa:
        return False
    try:
        from src.services.saas import licensing
        if licensing.estado_operativo(id_empresa) in _ESTADOS_EXENTOS:
            return True
    except Exception as e:
        logger.error("_empresa_exenta(%s): %s", id_empresa, e)
    return _exencion_web_cacheada(id_empresa)


def _proveedor_exento(id_suministrador) -> bool:
    """¿Está exento el PROVEEDOR vendedor (petición explícita, 2026-11-21: mismo criterio que la
    empresa compradora, visto desde el otro lado — un proveedor nunca tiene `id_empresa` local
    propio, ver docstring del módulo, así que solo puede resolverse vía su email de acceso)."""
    if not id_suministrador:
        return False
    return _exencion_proveedor_cacheada(id_suministrador)


def _pct_a_importe(importe_total, pct) -> float:
    try:
        importe_total = float(importe_total or 0)
    except (TypeError, ValueError):
        importe_total = 0.0
    return round(importe_total * pct / 100.0, 2)


def tiene_suscripcion_desktop_activa(id_empresa) -> bool:
    """Wrapper público de `_empresa_exenta` (petición explícita, 2026-11-24 — gatear "Alta
    artículos" del Portal B2B a empresas CON suscripción de escritorio): misma resolución exacta
    ("activa"/"prueba", local o vía sincronización web), reutilizada tal cual — cero lógica
    duplicada. Nombre público porque esta pregunta ya no es exclusiva de comisiones."""
    return _empresa_exenta(id_empresa)


def tiene_suscripcion_desktop_activa_proveedor(id_suministrador) -> bool:
    """Wrapper público de `_proveedor_exento` (petición explícita, 2026-11-27 — plan Freemium/de
    pago del Portal Proveedor, ver `services/portal_plan.py`): mismo criterio, lado proveedor."""
    return _proveedor_exento(id_suministrador)


def porcentaje_comprador(id_empresa) -> float:
    """% de recargo que paga la EMPRESA COMPRADORA sobre su propio pedido — depende EXCLUSIVAMENTE
    de si ELLA MISMA tiene una suscripción activa a Smart Manager; el estado del proveedor es
    irrelevante aquí (petición explícita 2026-11-21)."""
    return PCT_EXENTA if _empresa_exenta(id_empresa) else PCT_SIN_SUSCRIPCION


def porcentaje_proveedor(id_suministrador) -> float:
    """% de comisión que paga el PROVEEDOR sobre su propio cobro — depende EXCLUSIVAMENTE de si ÉL
    MISMO tiene una suscripción activa a Smart Manager; el estado de la empresa compradora es
    irrelevante aquí (petición explícita 2026-11-21)."""
    return PCT_EXENTA if _proveedor_exento(id_suministrador) else PCT_SIN_SUSCRIPCION


def calcular_comprador(id_empresa, importe_total) -> float:
    """Importe del recargo de la empresa compradora (misma divisa que `importe_total`), 2 decimales."""
    return _pct_a_importe(importe_total, porcentaje_comprador(id_empresa))


def calcular_proveedor(id_suministrador, importe_total) -> float:
    """Importe de la comisión del proveedor (misma divisa que `importe_total`), 2 decimales."""
    return _pct_a_importe(importe_total, porcentaje_proveedor(id_suministrador))


def desglose_comprador(id_empresa, importe_total) -> dict:
    """{base, porcentaje, recargo, total} — SOLO datos de la empresa compradora, para el Portal
    Empresa B2B. No incluye ni depende de ningún dato del proveedor."""
    try:
        base = float(importe_total or 0)
    except (TypeError, ValueError):
        base = 0.0
    pct = porcentaje_comprador(id_empresa)
    recargo = round(base * pct / 100.0, 2)
    return {"base": round(base, 2), "porcentaje": pct, "recargo": recargo,
            "total": round(base, 2)}


def desglose_proveedor(id_suministrador, importe_total) -> dict:
    """{base, porcentaje, comision, total} — SOLO datos del proveedor, para el Portal Proveedor. No
    incluye ni depende de ningún dato de la empresa compradora."""
    try:
        base = float(importe_total or 0)
    except (TypeError, ValueError):
        base = 0.0
    pct = porcentaje_proveedor(id_suministrador)
    comision = round(base * pct / 100.0, 2)
    return {"base": round(base, 2), "porcentaje": pct, "comision": comision,
            "total": round(base, 2)}


def recargos_transaccion(id_empresa, id_suministrador, importe_total) -> dict:
    """Uso INTERNO EXCLUSIVO de `b2b_escrow.py` — combina los dos lados, totalmente independientes
    entre sí, para una misma transacción: {recargo_comprador, comision_proveedor}. NINGÚN portal debe
    llamar a esta función ni mostrar sus dos valores juntos (cada portal solo ve su propio lado, vía
    `desglose_comprador`/`desglose_proveedor`)."""
    return {
        "recargo_comprador": calcular_comprador(id_empresa, importe_total),
        "comision_proveedor": calcular_proveedor(id_suministrador, importe_total),
    }
