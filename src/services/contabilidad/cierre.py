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
