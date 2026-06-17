"""
Libros de IVA y borrador del modelo 303 (E6.6) — derivados de los apuntes.

Libro de IVA repercutido (cuenta 477) y soportado (cuenta 472): cada apunte de IVA
lleva su `tipo_iva`; la base se reconstruye como cuota/(tipo/100). Las devoluciones
(IVA en el lado contrario) restan automáticamente. Borrador 303 = repercutido −
soportado. NO es presentación telemática (DC1).
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, _filas_a_dicts, obtener_conexion
from src.services.contabilidad import mapeo as M

logger = logging.getLogger("contab.iva")


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _base(cuota, tipo):
    try:
        t = float(tipo or 0)
        return round(float(cuota) / (t / 100), 2) if t else 0.0
    except Exception:
        return 0.0


def libro_iva(tipo="repercutido", id_empresa=None, anio=None, desde=None, hasta=None) -> dict:
    """Libro de IVA repercutido|soportado. Devuelve {lineas:[{fecha,numero,tipo_iva,
    base,cuota}], total_base, total_cuota}."""
    id_empresa = _empresa(id_empresa)
    cuenta = M.cuenta("iva_rep" if tipo == "repercutido" else "iva_sop", id_empresa=id_empresa)
    # repercutido: neto = haber-debe ; soportado: neto = debe-haber
    signo = "ap.haber-ap.debe" if tipo == "repercutido" else "ap.debe-ap.haber"
    filtros = ["ap.id_empresa=%s", "ap.codigo_cuenta=%s", "a.estado<>'borrador'"]
    params = [id_empresa, cuenta]
    if anio:
        filtros.append("a.anio=%s"); params.append(int(anio))
    if desde:
        filtros.append("a.fecha>=%s"); params.append(desde)
    if hasta:
        filtros.append("a.fecha<=%s"); params.append(hasta)
    lineas, tb, tc = [], 0.0, 0.0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT a.fecha, a.numero, a.ref_origen, ap.tipo_iva, ({signo}) AS cuota "
                "FROM contab_apuntes ap JOIN contab_asientos a ON a.id=ap.id_asiento "
                "WHERE " + " AND ".join(filtros) + " ORDER BY a.fecha, a.numero", tuple(params))
            for r in _filas_a_dicts(cur, cur.fetchall()):
                cuota = round(float(r["cuota"] or 0), 2)
                if cuota == 0:
                    continue
                base = _base(cuota, r["tipo_iva"])
                tb += base; tc += cuota
                lineas.append({"fecha": r["fecha"], "numero": r["numero"],
                               "ref": r["ref_origen"], "tipo_iva": float(r["tipo_iva"] or 0),
                               "base": base, "cuota": cuota})
    except Exception as e:
        logger.error("libro_iva(%s): %s", tipo, e)
    return {"tipo": tipo, "lineas": lineas, "total_base": round(tb, 2), "total_cuota": round(tc, 2)}


def resumen_303(id_empresa=None, anio=None, desde=None, hasta=None) -> dict:
    """Borrador del modelo 303 (cálculo): IVA devengado (repercutido) − deducible
    (soportado) = resultado. Sin presentación AEAT."""
    id_empresa = _empresa(id_empresa)
    rep = libro_iva("repercutido", id_empresa, anio, desde, hasta)
    sop = libro_iva("soportado", id_empresa, anio, desde, hasta)
    resultado = round(rep["total_cuota"] - sop["total_cuota"], 2)
    return {
        "iva_devengado_base": rep["total_base"], "iva_devengado_cuota": rep["total_cuota"],
        "iva_deducible_base": sop["total_base"], "iva_deducible_cuota": sop["total_cuota"],
        "resultado": resultado,
        "sentido": "a ingresar" if resultado >= 0 else "a compensar/devolver",
    }
