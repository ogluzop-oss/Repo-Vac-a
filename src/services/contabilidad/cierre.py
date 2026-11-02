"""
Cierre contable formal (F2.1) — Regularización, Cierre, Apertura y arrastre de saldos.

Completa el ciclo PGC anual REUTILIZANDO el núcleo de asientos (E6.2): no modifica
`asientos.py`, `posting.py` ni `mapeo.py`; solo orquesta `crear_asiento`.

Ciclo (ejercicio N):
  1. REGULARIZACIÓN  (fecha N-12-31, tipo='regularizacion'): salda grupos 6 y 7
     contra 129 «Resultado del ejercicio».
  2. CIERRE          (fecha N-12-31, tipo='cierre'): salda las cuentas patrimoniales
     (activo/pasivo/PN, incl. 129) → todas a cero en el ejercicio N.
  3. Se marca el ejercicio N como cerrado (reutiliza `cuentas.cerrar_ejercicio`).
  4. APERTURA        (fecha N+1-01-01, tipo='apertura'): invierte el asiento de cierre
     → arrastra los saldos al ejercicio N+1.

Cada asiento es auditable (hash encadenado del núcleo) y trazable: fecha,
fecha_registro (timestamp), usuario, tipo de operación, y ejercicio origen/destino
codificado en `ref_origen` ("ejercicio:N" / "ejercicio:N->N+1").
Multiempresa por id_empresa. Idempotente (no recierra ni duplica).
"""

import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _filas_a_dicts, obtener_conexion)
from src.services.contabilidad import cuentas as K
from src.services.contabilidad.asientos import crear_asiento, obtener_asiento

logger = logging.getLogger("contab.cierre")

_CUENTA_RESULTADO = "129"        # Resultado del ejercicio (PGC)
_TIPOS_PYG = ("gasto", "ingreso")
_EPS = 0.005                      # medio céntimo


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


def _saldos(id_empresa, anio, solo_tipos=None) -> list[dict]:
    """Saldo neto (debe-haber) por cuenta del ejercicio (no borrador). Filtra |saldo|>0.
    `solo_tipos`: si se indica, restringe a esos `contab_cuentas.tipo`."""
    filtros = ["ap.id_empresa=%s", "a.anio=%s", "a.estado<>'borrador'"]
    params = [id_empresa, int(anio)]
    sql = (
        "SELECT ap.codigo_cuenta, COALESCE(c.tipo,'otro') AS tipo, "
        "ROUND(SUM(ap.debe-ap.haber),2) AS saldo "
        "FROM contab_apuntes ap JOIN contab_asientos a ON a.id=ap.id_asiento "
        "LEFT JOIN contab_cuentas c ON c.id_empresa=ap.id_empresa AND c.codigo=ap.codigo_cuenta "
        "WHERE " + " AND ".join(filtros) + " GROUP BY ap.codigo_cuenta, tipo "
        "HAVING ABS(saldo) > %s ORDER BY ap.codigo_cuenta")
    params.append(_EPS)
    out = []
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        for r in _filas_a_dicts(cur, cur.fetchall()):
            if solo_tipos and r["tipo"] not in solo_tipos:
                continue
            out.append({"codigo": r["codigo_cuenta"], "tipo": r["tipo"],
                        "saldo": round(float(r["saldo"] or 0), 2)})
    return out


def _linea_saldar(codigo, saldo, descripcion):
    """Línea que ANULA el saldo de una cuenta: deudor→haber, acreedor→debe."""
    if saldo > 0:
        return {"codigo_cuenta": codigo, "descripcion": descripcion, "debe": 0.0, "haber": round(saldo, 2)}
    return {"codigo_cuenta": codigo, "descripcion": descripcion, "debe": round(-saldo, 2), "haber": 0.0}


def buscar_asiento(id_empresa, anio, tipo) -> dict | None:
    """Devuelve el asiento (cabecera) de un `tipo` para el ejercicio, si existe."""
    id_empresa = _empresa(id_empresa)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM contab_asientos WHERE id_empresa=%s AND anio=%s AND tipo=%s "
                    "AND estado<>'anulado' ORDER BY numero DESC LIMIT 1", (id_empresa, int(anio), tipo))
        filas = _filas_a_dicts(cur, cur.fetchall())
        return filas[0] if filas else None


# ── 1. Regularización ────────────────────────────────────────────────────────
def regularizar(anio, usuario=None, id_empresa=None) -> dict | None:
    """Salda grupos 6 (gastos) y 7 (ingresos) contra 129. None si no hay PyG."""
    id_empresa = _empresa(id_empresa)
    if K.ejercicio_cerrado(anio, id_empresa):
        logger.warning("regularizar: ejercicio %s cerrado", anio); return None
    filas = _saldos(id_empresa, anio, solo_tipos=_TIPOS_PYG)
    if not filas:
        return None
    lineas = [_linea_saldar(f["codigo"], f["saldo"], "Regularización P y G") for f in filas]
    diff = round(sum(l["debe"] for l in lineas) - sum(l["haber"] for l in lineas), 2)
    if diff > _EPS:                  # beneficio → 129 al haber
        lineas.append({"codigo_cuenta": _CUENTA_RESULTADO, "descripcion": "Resultado del ejercicio",
                       "debe": 0.0, "haber": diff})
    elif diff < -_EPS:              # pérdida → 129 al debe
        lineas.append({"codigo_cuenta": _CUENTA_RESULTADO, "descripcion": "Resultado del ejercicio",
                       "debe": -diff, "haber": 0.0})
    return crear_asiento(f"{anio}-12-31", lineas, concepto=f"Regularización ejercicio {anio}",
                         tipo="regularizacion", origen="cierre_ejercicio",
                         ref_origen=f"ejercicio:{anio}", usuario=usuario, id_empresa=id_empresa)


# ── 2. Asiento de cierre ─────────────────────────────────────────────────────
def asiento_cierre(anio, usuario=None, id_empresa=None) -> dict | None:
    """Salda TODAS las cuentas con saldo del ejercicio (patrimoniales tras regularizar)."""
    id_empresa = _empresa(id_empresa)
    if K.ejercicio_cerrado(anio, id_empresa):
        logger.warning("asiento_cierre: ejercicio %s cerrado", anio); return None
    filas = _saldos(id_empresa, anio)
    if not filas:
        return None
    lineas = [_linea_saldar(f["codigo"], f["saldo"], "Asiento de cierre") for f in filas]
    return crear_asiento(f"{anio}-12-31", lineas, concepto=f"Asiento de cierre {anio}",
                         tipo="cierre", origen="cierre_ejercicio",
                         ref_origen=f"ejercicio:{anio}", usuario=usuario, id_empresa=id_empresa)


# ── 3. Apertura del ejercicio siguiente (arrastre de saldos) ─────────────────
def asiento_apertura(anio_origen, usuario=None, id_empresa=None) -> dict | None:
    """Crea el asiento de apertura del ejercicio N+1 invirtiendo el cierre de N
    (arrastre de saldos de activo/pasivo/PN). None si no hay cierre."""
    id_empresa = _empresa(id_empresa)
    destino = int(anio_origen) + 1
    cierre = buscar_asiento(id_empresa, anio_origen, "cierre")
    if not cierre:
        logger.warning("asiento_apertura: sin cierre para %s", anio_origen); return None
    if buscar_asiento(id_empresa, destino, "apertura"):
        return buscar_asiento(id_empresa, destino, "apertura")     # idempotente
    det = obtener_asiento(cierre["id"], id_empresa) or {}
    lineas = [{"codigo_cuenta": ap["codigo_cuenta"], "descripcion": "Apertura del ejercicio",
               "debe": float(ap["haber"] or 0), "haber": float(ap["debe"] or 0),
               "tercero": ap.get("tercero")}
              for ap in det.get("apuntes", [])]
    if not lineas:
        return None
    K.crear_ejercicio(destino, id_empresa)        # asegura ejercicio destino abierto
    return crear_asiento(f"{destino}-01-01", lineas, concepto=f"Asiento de apertura {destino}",
                         tipo="apertura", origen="apertura_ejercicio",
                         ref_origen=f"ejercicio:{anio_origen}->{destino}", usuario=usuario,
                         id_empresa=id_empresa)


# ── Orquestador del cierre formal ────────────────────────────────────────────
def cerrar_ejercicio_formal(anio, usuario=None, id_empresa=None, abrir_siguiente=True) -> dict:
    """Ejecuta el ciclo completo: regularización → cierre → marca cerrado → apertura.

    Devuelve {ok, anio, destino, regularizacion, cierre, apertura, motivo?}.
    Idempotente: si el ejercicio ya está cerrado, no hace nada."""
    id_empresa = _empresa(id_empresa)
    anio = int(anio)
    ej = K.obtener_ejercicio(anio, id_empresa)
    if not ej:
        return {"ok": False, "motivo": "sin_ejercicio", "anio": anio}
    if K.ejercicio_cerrado(anio, id_empresa):
        return {"ok": False, "motivo": "ya_cerrado", "anio": anio}

    reg = regularizar(anio, usuario, id_empresa)
    cie = asiento_cierre(anio, usuario, id_empresa)
    cerrado = K.cerrar_ejercicio(anio, id_empresa)        # reutiliza el cierre básico existente
    ape = None
    if abrir_siguiente and cie:
        ape = asiento_apertura(anio, usuario, id_empresa)
    logger.info("Cierre formal ejercicio %s (empresa=%s): reg=%s cie=%s ape=%s",
                anio, id_empresa, bool(reg), bool(cie), bool(ape))
    return {"ok": bool(cerrado), "anio": anio, "destino": anio + 1,
            "regularizacion": reg, "cierre": cie, "apertura": ape}


def reabrir_ejercicio_formal(anio, usuario=None, id_empresa=None) -> dict:
    """Revierte un cierre formal: reabre el ejercicio y ANULA (mediante contraasiento — nunca
    borra, mismo criterio de inmutabilidad/auditoría que el resto del módulo) la apertura del
    ejercicio siguiente, el asiento de cierre y la regularización, en ese orden.

    Devuelve {ok, anio, apertura_anulada, cierre_anulado, regularizacion_anulada, motivo?}.
    Idempotente: si el ejercicio no está cerrado, no hace nada."""
    id_empresa = _empresa(id_empresa)
    anio = int(anio)
    if not K.ejercicio_cerrado(anio, id_empresa):
        return {"ok": False, "motivo": "no_cerrado", "anio": anio}

    destino = anio + 1
    # Guarda de integridad: si el ejercicio SIGUIENTE también está cerrado, sus saldos ya
    # arrastraron la apertura que estamos a punto de anular — hay que reabrir en orden, del más
    # reciente hacia atrás.
    if K.ejercicio_cerrado(destino, id_empresa):
        return {"ok": False, "motivo": "siguiente_cerrado", "anio": anio}

    ape_doc = buscar_asiento(id_empresa, destino, "apertura")
    cie_doc = buscar_asiento(id_empresa, anio, "cierre")
    reg_doc = buscar_asiento(id_empresa, anio, "regularizacion")

    # Reabrir PRIMERO: `asientos.anular()` exige que el ejercicio del asiento a anular NO esté
    # cerrado (los de cierre/regularización pertenecen a `anio`, que seguía cerrado hasta ahora).
    K.reabrir_ejercicio(anio, id_empresa)

    from src.services.contabilidad.asientos import anular as _anular
    # `fecha` EXPLÍCITA (no el "hoy" por defecto de `anular()`): el contraasiento debe fecharse
    # DENTRO del propio ejercicio del asiento que revierte. Si se dejara el "hoy" por defecto,
    # `crear_asiento` lo rechazaría en cuanto la fecha real del sistema cayera dentro de OTRO
    # ejercicio ya cerrado (p. ej. el propio `anio` antes de esta reapertura) — no es un caso raro,
    # es la situación normal cuando se reabre un ejercicio bastante después de haberlo cerrado.
    ape_anulada = _anular(ape_doc["id"], fecha=f"{destino}-01-01", usuario=usuario,
                         id_empresa=id_empresa) if ape_doc else None
    cie_anulado = _anular(cie_doc["id"], fecha=f"{anio}-12-31", usuario=usuario,
                         id_empresa=id_empresa) if cie_doc else None
    reg_anulada = _anular(reg_doc["id"], fecha=f"{anio}-12-31", usuario=usuario,
                         id_empresa=id_empresa) if reg_doc else None

    logger.info("Reapertura ejercicio %s (empresa=%s): ape=%s cie=%s reg=%s",
                anio, id_empresa, bool(ape_anulada), bool(cie_anulado), bool(reg_anulada))
    return {"ok": True, "anio": anio, "apertura_anulada": ape_anulada,
            "cierre_anulado": cie_anulado, "regularizacion_anulada": reg_anulada}


# ── Validaciones previas al cierre formal ────────────────────────────────────
def _asientos_descuadrados(id_empresa) -> list[dict]:
    """`contab_asientos` (de ESTA empresa, cualquier ejercicio, no anulados) cuyo total_debe no
    coincide con total_haber. En circuito normal esto NUNCA debería ocurrir — `asientos.
    crear_asiento` rechaza (devuelve `None`) cualquier intento de crear un asiento descuadrado
    antes de persistirlo — pero se valida igualmente aquí como red de seguridad defensiva ante
    datos corruptos/importados/editados directamente en BD (mismo criterio que `cadena_auditoria_
    valida`: comprobar, no asumir)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, numero, anio, fecha, concepto, total_debe, total_haber FROM "
                "contab_asientos WHERE id_empresa=%s AND estado<>'anulado' "
                "AND ABS(total_debe - total_haber) > %s ORDER BY anio, numero",
                (id_empresa, _EPS))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("_asientos_descuadrados: %s", e)
        return []


def validar_cierre(anio, id_empresa=None) -> dict:
    """Validaciones PRE-cierre del ejercicio `anio`: {"ok": bool, "bloqueantes": [...],
    "avisos": [...]}. `ok=False` (con `bloqueantes` no vacío) debe impedir que la GUI/caller
    invoque `cerrar_ejercicio_formal` — son fallos reales de corrección contable, no opiniones.
    `avisos` es solo informativo (huecos ya conocidos/honestos de otros módulos, p.ej. `memoria_
    anual`/`propuesta_resultado`) y NUNCA bloquea el cierre.

    No introduce ningún cálculo nuevo más allá de la propia validación: reutiliza `cuentas.
    ejercicio_cerrado`, `memoria_anual.generar_memoria`, `propuesta_resultado.
    calcular_propuesta_aplicacion` y `estado_flujos.generar_estado_flujos` tal cual."""
    id_empresa = _empresa(id_empresa)
    anio = int(anio)
    bloqueantes, avisos = [], []

    # ── Bloqueantes ──────────────────────────────────────────────────────────
    descuadrados = _asientos_descuadrados(id_empresa)
    for a in descuadrados:
        bloqueantes.append(
            f"Asiento nº{a['numero']} del ejercicio {a['anio']} ({a.get('concepto') or 's/concepto'}, "
            f"{a.get('fecha')}) está DESCUADRADO: debe={a['total_debe']} haber={a['total_haber']} "
            "— no se puede cerrar el ejercicio con asientos que incumplen la partida doble.")

    ej_anterior = K.obtener_ejercicio(anio - 1, id_empresa)
    if ej_anterior and not K.ejercicio_cerrado(anio - 1, id_empresa):
        bloqueantes.append(
            f"El ejercicio anterior ({anio - 1}) existe pero NO está cerrado formalmente — "
            f"los ejercicios deben cerrarse en orden (cerrar primero {anio - 1}).")

    # ── Avisos (no bloquean) ─────────────────────────────────────────────────
    try:
        from src.services.contabilidad.memoria_anual import generar_memoria
        memoria = generar_memoria(anio, id_empresa=id_empresa) or {}
        avisos.extend(memoria.get("actividad_empresa", {}).get("avisos") or [])
        if not (memoria.get("partes_vinculadas", {}).get("operaciones")):
            avisos.append(
                "No hay operaciones con partes vinculadas registradas en el ejercicio "
                "(informativo: puede ser correcto si no ha habido ninguna).")
    except Exception as e:
        logger.warning("validar_cierre: memoria_anual no disponible: %s", e)

    try:
        from src.services.contabilidad.propuesta_resultado import calcular_propuesta_aplicacion
        propuesta = calcular_propuesta_aplicacion(anio, id_empresa=id_empresa) or {}
        avisos.extend(propuesta.get("avisos") or [])
    except Exception as e:
        logger.warning("validar_cierre: propuesta_resultado no disponible: %s", e)

    try:
        from src.services.contabilidad.estado_flujos import generar_estado_flujos
        ef = generar_estado_flujos(anio, id_empresa=id_empresa) or {}
        fin = ef.get("financiacion", {})
        if not any(abs(float(fin.get(k) or 0)) > 0.01 for k in
                  ("variacion_deuda_financiera", "variacion_capital_y_aportaciones",
                   "dividendos_pagados")):
            avisos.append(
                "Sin movimientos en el flujo de financiación del ejercicio (informativo: puede "
                "ser correcto si no ha habido altas/bajas de deuda ni aportaciones de capital).")
    except Exception as e:
        logger.warning("validar_cierre: estado_flujos no disponible: %s", e)

    return {"ok": not bloqueantes, "anio": anio, "id_empresa": id_empresa,
            "bloqueantes": bloqueantes, "avisos": avisos}
