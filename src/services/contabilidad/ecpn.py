"""
Estado de Cambios en el Patrimonio Neto (ECPN) — Cuentas Anuales, pieza 2 de 3 (junto a
`balance_situacion.py` y `estado_flujos.py`). Reutiliza EXCLUSIVAMENTE `balance_situacion.
generar_balance()` para los saldos de PN a inicio y fin de `anio` — no se recalculan saldos
aquí; este módulo solo compara los DOS balances (31/12 de `anio-1` y 31/12 de `anio`) línea a
línea por partida de patrimonio neto.

Partidas que compara (las mismas que expone `generar_balance`):
  capital, prima_emision, otros_instrumentos_patrimonio, otras_aportaciones_socios, reservas,
  acciones_propias_resta, resultados_ejercicios_anteriores, resultado_del_ejercicio (A-1,
  Fondos propios) + subvenciones_y_ajustes (A-2/A-3).

Nota sobre `cierre.cerrar_ejercicio_formal`: su regularización SOLO salda grupos 6/7 contra
129 — NO existe (todavía) ninguna dotación automática de reserva legal ni reparto de
resultado (eso es la "Propuesta de Aplicación del Resultado", responsabilidad de otro
desarrollo en curso, ver auditoría de esta tarea). Por eso aquí NO se inventa una línea de
"dotación a reserva legal": si en algún momento se postea una (vía un asiento normal que
mueva 112), aparecerá SOLA como una variación real de la partida "reservas" entre los dos
balances — se refleja con datos reales, nunca se fabrica.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID
from src.services.contabilidad import balance_situacion as Bal

logger = logging.getLogger("contab.ecpn")


def _empresa(id_empresa=None):
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


def _lineas_fp(balance) -> dict:
    """{linea: importe} de fondos_propios de un `generar_balance()`, SIN la clave 'total' ni
    los cajones genéricos de `_clasificar` (se añaden aparte, con su propia clave real)."""
    fp = dict(balance["pn_pasivo"]["patrimonio_neto"]["fondos_propios"])
    fp.pop("total", None)
    return fp


def generar_ecpn(anio, id_empresa=None) -> dict:
    """Estado de Cambios en el Patrimonio Neto del ejercicio `anio`: saldo inicial (balance a
    31/12 de `anio-1`), movimientos del año (delta real línea a línea) y saldo final (balance
    a 31/12 de `anio`). {lineas: {linea: {inicial, movimiento, final}}, pn_inicial, pn_final,
    total_movimientos, cuadra, diferencia, advertencias}."""
    id_empresa = _empresa(id_empresa)
    anio = int(anio)
    advertencias = []

    b_ini = Bal.generar_balance(anio - 1, id_empresa=id_empresa)
    b_fin = Bal.generar_balance(anio, id_empresa=id_empresa)
    for etiqueta, b in ((anio - 1, b_ini), (anio, b_fin)):
        if not b["cuadra"]:
            advertencias.append(f"El balance de {etiqueta} no cuadra (diferencia {b['diferencia']} €) "
                                "— el ECPN hereda esa inconsistencia.")

    fp_ini, fp_fin = _lineas_fp(b_ini), _lineas_fp(b_fin)
    ajustes_ini = b_ini["pn_pasivo"]["patrimonio_neto"]["ajustes_y_subvenciones"].get("total", 0.0)
    ajustes_fin = b_fin["pn_pasivo"]["patrimonio_neto"]["ajustes_y_subvenciones"].get("total", 0.0)

    lineas = {}
    for clave in sorted(set(fp_ini) | set(fp_fin)):
        ini = round(fp_ini.get(clave, 0.0), 2)
        fin = round(fp_fin.get(clave, 0.0), 2)
        lineas[clave] = {"inicial": ini, "movimiento": round(fin - ini, 2), "final": fin}
    lineas["ajustes_y_subvenciones"] = {"inicial": round(ajustes_ini, 2),
                                        "movimiento": round(ajustes_fin - ajustes_ini, 2),
                                        "final": round(ajustes_fin, 2)}

    pn_inicial = b_ini["pn_pasivo"]["patrimonio_neto"]["total"]
    pn_final = b_fin["pn_pasivo"]["patrimonio_neto"]["total"]
    total_movimientos = round(sum(v["movimiento"] for v in lineas.values()), 2)
    diferencia = round(pn_inicial + total_movimientos - pn_final, 2)
    cuadra = abs(diferencia) < 0.01
    if not cuadra:
        logger.error("generar_ecpn(%s, empresa=%s): NO RECONCILIA — pn_inicial=%s + "
                     "movimientos=%s != pn_final=%s (diferencia=%s)",
                     anio, id_empresa, pn_inicial, total_movimientos, pn_final, diferencia)
        advertencias.append(f"Inicial + movimientos no reconcilia con final: diferencia {diferencia} €.")

    return {
        "anio": anio, "id_empresa": id_empresa,
        "lineas": lineas,
        "pn_inicial": pn_inicial, "pn_final": pn_final,
        "total_movimientos": total_movimientos,
        "resultado_del_ejercicio_anterior": b_ini.get("resultado_del_ejercicio", 0.0),
        "resultado_del_ejercicio": b_fin.get("resultado_del_ejercicio", 0.0),
        "cuadra": cuadra, "diferencia": diferencia, "advertencias": advertencias,
    }
