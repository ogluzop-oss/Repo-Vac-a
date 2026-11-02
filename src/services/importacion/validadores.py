"""
Validadores de entidad para el motor de migración por etapas (`motor.py::validate`).

Estilo FUNCIONAL, igual que `modelo.py`/`mapeo.py` (sin clases: un diccionario `entidad -> función` en
vez de un `CustomerValidator`/`ProductValidator` por clase — así encaja con el resto del módulo, que no
usa OOP para esto). Cada validador recibe una fila YA MAPEADA a campos canónicos (la salida de
`mapeo.aplicar_mapeo`) y devuelve una lista de hallazgos `{campo, valor, motivo, severidad}` —
`severidad` en `{"error", "advertencia"}` — con la MISMA forma que necesita `import_trabajos_errores`
(task 1) para no tener que traducir nada entre capas.

Tres bloques de reglas, de más genérico a más específico (mismo orden que pide el negocio):
1. Tipos de datos y formato (fechas/números/obligatorios) — reutilizable, dirigido por `modelo.CAMPOS`.
2. Integridad referencial (familia de PRODUCTOS, cuenta contable de SALDOS).
3. Reglas de negocio ERP (NIF/CIF de terceros, IBAN de tesorería).

`construir_contexto()` precarga UNA vez por lote los datos de referencia (familias/cuentas existentes)
que si no se cachearan obligarían a una consulta a BD por cada fila.
"""

import logging

from src.services.importacion.modelo import (
    CAMPOS, CLIENTES, PLAN_CONTABLE, PRODUCTOS, PROVEEDORES, SALDOS, TESORERIA, VENTAS_HIST,
    limpiar_texto, parse_fecha, parse_precio, parse_stock,
)
from src.utils import iban as _iban
from src.utils.nif_cif import validar_documento_fiscal

logger = logging.getLogger("importacion.validadores")


def _hallazgo(campo, valor, motivo, severidad="error") -> dict:
    return {"campo": campo, "valor": (None if valor is None else str(valor)[:500]),
            "motivo": motivo, "severidad": severidad}


# ── 1) Tipos de datos y formato (genérico, dirigido por CAMPOS) ─────────────────────────────────
def validar_requeridos_y_formato(datos, entidad) -> list:
    """Recorre `modelo.CAMPOS[entidad]`: obligatorios vacíos, fechas no parseables, numéricos no
    parseables (según el propio nombre del campo canónico: fecha* -> parse_fecha, cantidad/importe/
    precio/debe/haber/saldo -> parse_precio). Válido para las 7 entidades sin tener que repetirlo."""
    hallazgos = []
    defs = CAMPOS.get(entidad, {})
    for campo, (requerido, _sin) in defs.items():
        valor = datos.get(campo)
        vacio = not limpiar_texto(valor)
        if requerido and vacio:
            hallazgos.append(_hallazgo(campo, valor, f"campo obligatorio vacío: {campo}", "error"))
            continue
        if vacio:
            continue
        if campo == "fecha" and parse_fecha(valor) is None:
            hallazgos.append(_hallazgo(campo, valor, "fecha no reconocible", "error"))
        elif campo in ("precio", "cantidad", "importe", "debe", "haber", "saldo") and \
                parse_precio(valor) is None:
            hallazgos.append(_hallazgo(campo, valor, f"valor numérico no reconocible: {campo}", "error"))
        elif campo in ("stock", "stock_central", "stock_esperado") and parse_stock(valor) is None:
            hallazgos.append(_hallazgo(campo, valor, "stock no reconocible (numérico esperado)", "error"))
    return hallazgos


# ── 2) Contexto de referencia (precargado UNA vez por lote) ─────────────────────────────────────
def construir_contexto(entidad, id_empresa=None) -> dict:
    """Precarga los datos de referencia que necesita `validar_fila` para no consultar la BD fila a
    fila. Best-effort: si la consulta de referencia falla, el contexto queda vacío (el validador
    entonces no puede confirmar la referencia y la marca como advertencia, nunca revienta)."""
    ctx = {"familias_conocidas": set(), "cuentas_conocidas": set()}
    if entidad == PRODUCTOS:
        try:
            from src.db.familias import listar_familias
            ctx["familias_conocidas"] = {str(f.get("nombre") or "").strip().lower()
                                         for f in listar_familias(id_empresa, solo_activas=False)}
        except Exception as e:
            logger.debug("construir_contexto familias: %s", e)
    elif entidad == SALDOS:
        try:
            from src.services.contabilidad.cuentas import listar_cuentas
            ctx["cuentas_conocidas"] = {str(c.get("codigo") or "").strip()
                                        for c in listar_cuentas(id_empresa)}
        except Exception as e:
            logger.debug("construir_contexto cuentas: %s", e)
    return ctx


def _familias_vistas_en_lote(datos, contexto) -> set:
    """Nombres de familia que YA aparecieron en filas anteriores del mismo lote (se registran aquí,
    ver `validar_producto`) — junto a `familias_conocidas` cubre el 'se creará en este mismo lote'."""
    return contexto.setdefault("_familias_vistas", set())


# ── 3) Reglas de negocio ERP por entidad ─────────────────────────────────────────────────────────
def validar_producto(datos, *, id_empresa=None, contexto=None) -> list:
    contexto = contexto if contexto is not None else {}
    hallazgos = validar_requeridos_y_formato(datos, PRODUCTOS)
    familia = limpiar_texto(datos.get("familia"))
    if familia:
        key = familia.lower()
        conocidas = contexto.get("familias_conocidas", set())
        vistas = _familias_vistas_en_lote(datos, contexto)
        if key not in conocidas and key not in vistas:
            # Integridad referencial: NO es un fallo bloqueante — `_resolver_familias` hace
            # get-or-create, así que esta familia se CREARÁ sola al ejecutar `commit()`. Se informa
            # como advertencia (trazabilidad), nunca como error ("no hard-fail on will exist").
            hallazgos.append(_hallazgo("familia", familia,
                                       "familia nueva: se creará automáticamente al confirmar", "advertencia"))
        vistas.add(key)
    return hallazgos


def validar_terceros(datos, *, id_empresa=None, contexto=None, entidad=CLIENTES) -> list:
    hallazgos = validar_requeridos_y_formato(datos, entidad)
    nif = limpiar_texto(datos.get("nif"))
    if nif:
        ok, tipo = validar_documento_fiscal(nif)
        if tipo == "desconocido":
            hallazgos.append(_hallazgo("nif", nif,
                                       "formato de documento fiscal no reconocido (¿NIF/CIF extranjero?)",
                                       "advertencia"))
        elif not ok:
            hallazgos.append(_hallazgo("nif", nif, f"{tipo} inválido (dígito de control incorrecto)", "error"))
    return hallazgos


def validar_cliente(datos, *, id_empresa=None, contexto=None) -> list:
    return validar_terceros(datos, id_empresa=id_empresa, contexto=contexto, entidad=CLIENTES)


def validar_proveedor(datos, *, id_empresa=None, contexto=None) -> list:
    return validar_terceros(datos, id_empresa=id_empresa, contexto=contexto, entidad=PROVEEDORES)


def validar_ventas_hist(datos, *, id_empresa=None, contexto=None) -> list:
    return validar_requeridos_y_formato(datos, VENTAS_HIST)


def validar_saldos(datos, *, id_empresa=None, contexto=None) -> list:
    contexto = contexto if contexto is not None else {}
    hallazgos = validar_requeridos_y_formato(datos, SALDOS)
    cuenta = limpiar_texto(datos.get("cuenta"))
    debe = parse_precio(datos.get("debe")) if datos.get("debe") not in (None, "") else None
    haber = parse_precio(datos.get("haber")) if datos.get("haber") not in (None, "") else None
    saldo = parse_precio(datos.get("saldo")) if datos.get("saldo") not in (None, "") else None
    if (debe or 0) == 0 and (haber or 0) == 0 and (saldo or 0) == 0:
        hallazgos.append(_hallazgo("saldo", None, "sin importe (debe/haber/saldo todos vacíos o cero)",
                                   "error"))
    if cuenta:
        conocidas = contexto.get("cuentas_conocidas", set())
        if conocidas and cuenta not in conocidas:
            # Regla de negocio ERP: a diferencia de la familia de PRODUCTOS, el Plan Contable NO se
            # crea solo — `crear_asiento` exige que la cuenta YA exista (`services/contabilidad`). Si
            # no está en el plan contable real, es un error concreto y accionable, no una advertencia.
            hallazgos.append(_hallazgo("cuenta", cuenta,
                                       f"la cuenta contable '{cuenta}' no existe en el Plan Contable "
                                       "(impórtalo primero con la entidad PLAN_CONTABLE)", "error"))
        elif not conocidas:
            hallazgos.append(_hallazgo("cuenta", cuenta,
                                       "no se pudo comprobar contra el Plan Contable (sin cuentas dadas "
                                       "de alta todavía)", "advertencia"))
    return hallazgos


def validar_tesoreria(datos, *, id_empresa=None, contexto=None) -> list:
    hallazgos = validar_requeridos_y_formato(datos, TESORERIA)
    iban = limpiar_texto(datos.get("iban"))
    if iban and not _iban.validar_iban(iban):
        hallazgos.append(_hallazgo("iban", iban, "IBAN inválido (dígito de control mód-97 incorrecto)",
                                   "error"))
    bic = limpiar_texto(datos.get("bic"))
    if bic and not _iban.validar_bic(bic):
        hallazgos.append(_hallazgo("bic", bic, "BIC/SWIFT con formato inválido", "error"))
    return hallazgos


def validar_plan_contable(datos, *, id_empresa=None, contexto=None) -> list:
    return validar_requeridos_y_formato(datos, PLAN_CONTABLE)


_VALIDADORES = {
    PRODUCTOS: validar_producto,
    CLIENTES: validar_cliente,
    PROVEEDORES: validar_proveedor,
    VENTAS_HIST: validar_ventas_hist,
    SALDOS: validar_saldos,
    TESORERIA: validar_tesoreria,
    PLAN_CONTABLE: validar_plan_contable,
}


def validar_fila(entidad, datos_mapeados, *, id_empresa=None, contexto=None) -> list:
    """Punto único de entrada: valida UNA fila ya mapeada de `entidad`. Devuelve `[]` si no hay
    hallazgos (fila válida). Entidad desconocida -> `[]` (no bloquea; `motor.py` ya valida la entidad
    antes de llegar aquí)."""
    fn = _VALIDADORES.get(entidad)
    if not fn:
        return []
    try:
        return fn(datos_mapeados, id_empresa=id_empresa, contexto=contexto)
    except Exception as e:
        logger.error("validar_fila(%s): %s", entidad, e)
        return [_hallazgo(None, None, f"error interno de validación: {e}", "error")]


def estado_desde_hallazgos(hallazgos) -> str:
    """`error` si hay algún hallazgo de severidad error; `advertencia` si solo hay advertencias;
    `valido` si la lista está vacía."""
    if any(h["severidad"] == "error" for h in hallazgos):
        return "error"
    if hallazgos:
        return "advertencia"
    return "valido"
