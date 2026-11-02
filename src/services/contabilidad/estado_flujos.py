"""
Estado de Flujos de Efectivo (EFE) — Cuentas Anuales, pieza 3 de 3 (junto a
`balance_situacion.py` y `ecpn.py`). MÉTODO INDIRECTO (el que usa la inmensa mayoría de
PYMES españolas): se deriva ÍNTEGRAMENTE de `balance_situacion.generar_balance()` (deltas
Activo/Pasivo/PN entre `anio-1` y `anio`) + `perdidas_ganancias` — NO requiere un subsistema
nuevo de clasificación de movimientos bancarios por actividad (eso sería el método directo,
fuera de alcance; ver `tesoreria/cashflow.py`, que es una herramienta de PREVISIÓN de
tesorería por periodo, NO el EFE formal — no se reutiliza ni se confunde con él).

Esqueleto (PGC, indirecto):
  Explotación   = resultado del ejercicio + amortización del inmovilizado (ajuste no
                  monetario, dato REAL de `inmovilizado_amortizaciones`) +/- variación del
                  capital circulante (existencias/deudores/acreedores — deltas reales de
                  `generar_balance`).
  Inversión     = -compra de activos (capex REAL: `gmao.activos.gastos_activos_periodo()` +
                  altas en `inmovilizado_activos` — ver nota de las DOS fuentes reales de
                  capex que coexisten en este código, más abajo) +/- venta de activos (NO
                  trackeada, ver advertencia) +/- variación de inversiones financieras c/p.
  Financiación  = variación de deudas financieras (largo+corto) + variación de capital
                  social (delta real del propio balance) - dividendos pagados (NO trackeado,
                  ver advertencia — Fase "Propuesta de Aplicación del Resultado", otro
                  desarrollo en curso, puede introducir esta trazabilidad).

Conciliación OBLIGATORIA (nunca se oculta): la suma de los tres flujos "limpios" de arriba
puede NO explicar el 100% de la variación REAL de efectivo (cuentas 57x) si, por ejemplo,
una compra de inmovilizado se pagó en efectivo pero NUNCA se contabilizó en el grupo 2 (p.
ej. `finanzas.inmovilizado.alta_activo()` NO postea ningún asiento — solo
`dotar_amortizacion()` lo hace, vía la cola existente). Ese residuo se calcula SIEMPRE
(`ajuste_conciliacion`) y se expone sin disimularlo; si es significativo, se loguea como
error (nunca se fuerza a cero) — es una pista real de que hay movimientos de caja sin
reflejo contable en el grupo correspondiente, no un fallo de este módulo.

Dos fuentes de capex reales en este código: `gmao.activos` (tabla `activos`, altas de
maquinaria/vehículo — registro de MANTENIMIENTO) y `finanzas.inmovilizado` (tabla
`inmovilizado_activos`, registro CONTABLE de amortización). Auditoría de doble cómputo
(cierre de la brecha señalada anteriormente): no existe FK/clave compartida IMPUESTA por el
esquema entre ambas tablas (`activos.codigo` y `inmovilizado_activos.codigo` son columnas
independientes, y ningún flujo de alta existente — ni `gmao.activos.crear_activo`, ni
`finanzas.inmovilizado.alta_activo`, ni `transporte.crear_vehiculo` — escribe en la otra
tabla), pero SÍ es un escenario real de negocio que la MISMA compra física (p. ej. una
furgoneta) se dé de alta en ambos registros: uno para programar su mantenimiento (GMAO) y
otro para calcular su amortización contable (Finanzas) — y si el usuario usa el mismo
`codigo` en los dos (convención natural: la matrícula/código interno del activo), sumar
ambas fuentes tal cual duplicaría esa compra en el flujo de inversión. `_capex_periodo()`
cruza ambas listas por `codigo` (normalizado, case-insensitive): cuando coincide, cuenta la
compra UNA sola vez (se queda con el importe de `inmovilizado_activos` — es el registro
contable, con `cuenta_contable` real y ligado al motor de amortización que alimenta el
propio Balance, mientras que `activos.coste_adquisicion` es un campo informativo de ficha
técnica sin ese vínculo contable). Sin `codigo` compartido (caso igual de real: activos solo
en GMAO, o solo capitalizados en Finanzas) se siguen sumando ambas, sin infravalorar nada.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.contabilidad import balance_situacion as Bal

logger = logging.getLogger("contab.estado_flujos")

# Partidas de capital circulante (operativo) — activo corriente SIN efectivo ni inversiones
# financieras a corto plazo (estas últimas se tratan como inversión, no como circulante puro).
_WC_ACTIVO = ("existencias", "deudores_comerciales", "otros_deudores", "hp_deudora",
              "periodificaciones", "otros_activo_corriente")
_WC_PASIVO_CORRIENTE = ("acreedores_comerciales", "hp_ss_acreedoras", "periodificaciones",
                        "provisiones", "otras_deudas")
_WC_PASIVO_NO_CORRIENTE_OPERATIVO = ("provisiones", "pasivo_impuesto_diferido")
# Deuda financiera / intercompany → financiación (no circulante operativo).
_FIN_PASIVO_CORRIENTE = ("deudas_financieras_corto_plazo", "deudas_grupo_corto_plazo")
_FIN_PASIVO_NO_CORRIENTE = ("deudas_financieras_largo_plazo", "deudas_grupo_largo_plazo",
                            "deudas_largo_plazo_otras")
# Fondos propios que representan aportaciones/retiradas de socios (financiación), nunca
# resultado/reservas (que ya están en explotación / no son flujo de caja de financiación).
_FIN_FONDOS_PROPIOS = ("capital", "prima_emision", "otras_aportaciones_socios",
                       "acciones_propias_resta")


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


def _amortizacion_periodo(id_empresa, anio) -> float:
    """Amortización REAL dotada en `anio` (tabla `inmovilizado_amortizaciones`, dotada=1).
    Dato posteado por `finanzas.inmovilizado.dotar_amortizacion` — no se recalcula ni se
    estima; si nada se ha dotado todavía, es honestamente 0."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(importe),0) FROM inmovilizado_amortizaciones "
                "WHERE id_empresa<=>%s AND dotada=1 AND periodo BETWEEN %s AND %s",
                (id_empresa, f"{anio}-01", f"{anio}-12"))
            r = cur.fetchone()
            val = r[0] if not isinstance(r, dict) else list(r.values())[0]
            return round(float(val or 0), 2)
    except Exception as e:
        logger.error("_amortizacion_periodo(%s): %s", anio, e)
        return 0.0


def _filas_capex_inmovilizado(id_empresa, anio) -> list[dict]:
    """Altas REALES de `inmovilizado_activos` (finanzas) con `fecha_alta` dentro de `anio`,
    fila a fila (con `codigo`, para poder cruzar con `gmao.activos` — ver docstring del
    módulo)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, valor_adquisicion FROM inmovilizado_activos "
                "WHERE id_empresa<=>%s AND fecha_alta BETWEEN %s AND %s "
                "AND valor_adquisicion IS NOT NULL AND valor_adquisicion > 0",
                (id_empresa, f"{anio}-01-01", f"{anio}-12-31"))
            from src.db.conexion import _filas_a_dicts
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("_filas_capex_inmovilizado(%s): %s", anio, e)
        return []


def _filas_capex_gmao(id_empresa, anio) -> list[dict]:
    """Altas REALES de `gmao.activos` (maquinaria/vehículo) con coste de adquisición dentro
    de `anio`, fila a fila. Reutiliza `gastos_activos_periodo` tal cual (instrucción
    explícita: NO se recalcula)."""
    try:
        from src.services.gmao.activos import gastos_activos_periodo
        return gastos_activos_periodo(f"{anio}-01-01", f"{anio}-12-31", id_empresa=id_empresa)
    except Exception as e:
        logger.error("_filas_capex_gmao(%s): %s", anio, e)
        return []


def _capex_periodo(id_empresa, anio) -> dict:
    """Capex REAL del periodo, DEDUPLICADO entre las dos fuentes (ver docstring del módulo —
    hallazgo de auditoría de doble cómputo, ya resuelto aquí): si una fila de `gmao.activos`
    y una de `inmovilizado_activos` comparten `codigo` (normalizado: trim + minúsculas), se
    asume la MISMA compra física y se cuenta UNA sola vez (con el importe de
    `inmovilizado_activos`, el registro contable). Sin `codigo` compartido, ambas fuentes se
    siguen sumando íntegramente (compras genuinamente distintas, o un activo que solo existe
    en uno de los dos registros)."""
    filas_gmao = _filas_capex_gmao(id_empresa, anio)
    filas_fin = _filas_capex_inmovilizado(id_empresa, anio)
    cod_fin = {str(f["codigo"]).strip().lower() for f in filas_fin if f.get("codigo")}
    total_fin = round(sum(float(f["valor_adquisicion"] or 0) for f in filas_fin), 2)

    total_gmao_sin_duplicar = 0.0
    duplicados = []
    for f in filas_gmao:
        cod = str(f.get("codigo") or "").strip().lower()
        if cod and cod in cod_fin:
            duplicados.append({"codigo": f.get("codigo"), "concepto": f.get("concepto"),
                               "importe": float(f.get("importe") or 0)})
            continue
        total_gmao_sin_duplicar = round(total_gmao_sin_duplicar + float(f.get("importe") or 0), 2)

    return {
        "capex_gmao": total_gmao_sin_duplicar, "capex_inmovilizado_finanzas": total_fin,
        "total": round(total_gmao_sin_duplicar + total_fin, 2),
        "duplicados_excluidos": duplicados,
    }


def generar_estado_flujos(anio, id_empresa=None) -> dict:
    """EFE (método indirecto) del ejercicio `anio`. Devuelve explotación/inversión/
    financiación (con su detalle), la variación neta CALCULADA, la variación neta REAL de
    efectivo (cuentas 57x, delta del propio balance), el `ajuste_conciliacion` entre ambas
    (nunca oculto) y `cuadra`/`advertencias`."""
    id_empresa = _empresa(id_empresa)
    anio = int(anio)
    advertencias = []

    b0 = Bal.generar_balance(anio - 1, id_empresa=id_empresa)
    b1 = Bal.generar_balance(anio, id_empresa=id_empresa)
    for etiqueta, b in ((anio - 1, b0), (anio, b1)):
        if not b["cuadra"]:
            advertencias.append(f"El balance de {etiqueta} no cuadra (diferencia {b['diferencia']} €) "
                                "— el EFE hereda esa inconsistencia.")

    ac0, ac1 = b0["activo"]["corriente"], b1["activo"]["corriente"]
    pc0, pc1 = b0["pn_pasivo"]["pasivo_corriente"], b1["pn_pasivo"]["pasivo_corriente"]
    pnc0, pnc1 = b0["pn_pasivo"]["pasivo_no_corriente"], b1["pn_pasivo"]["pasivo_no_corriente"]
    fp0 = b0["pn_pasivo"]["patrimonio_neto"]["fondos_propios"]
    fp1 = b1["pn_pasivo"]["patrimonio_neto"]["fondos_propios"]

    def _d(d1, d0, clave):
        return round(d1.get(clave, 0.0) - d0.get(clave, 0.0), 2)

    # ── Explotación ──────────────────────────────────────────────────────────────────
    resultado = b1["resultado_del_ejercicio"]
    amortizacion = _amortizacion_periodo(id_empresa, anio)
    delta_wc_activo = round(sum(_d(ac1, ac0, k) for k in _WC_ACTIVO), 2)
    delta_wc_pasivo = round(sum(_d(pc1, pc0, k) for k in _WC_PASIVO_CORRIENTE)
                           + sum(_d(pnc1, pnc0, k) for k in _WC_PASIVO_NO_CORRIENTE_OPERATIVO), 2)
    variacion_capital_circulante = round(-delta_wc_activo + delta_wc_pasivo, 2)
    flujo_explotacion = round(resultado + amortizacion + variacion_capital_circulante, 2)

    # ── Inversión ────────────────────────────────────────────────────────────────────
    capex = _capex_periodo(id_empresa, anio)
    capex_gmao, capex_finanzas = capex["capex_gmao"], capex["capex_inmovilizado_finanzas"]
    venta_activos = 0.0   # NO trackeado en ningún motor existente (ver docstring) — honesto, no inventado.
    delta_inv_financieras_cp = _d(ac1, ac0, "inversiones_financieras_corto_plazo")
    flujo_inversion = round(-(capex_gmao + capex_finanzas) + venta_activos - delta_inv_financieras_cp, 2)
    if capex_gmao or capex_finanzas:
        advertencias.append("venta_activos=0: la baja de inmovilizado (`inmovilizado.baja_activo`) "
                            "no registra ningún importe de venta/cobro — si ha habido ventas reales "
                            "de activos en el periodo, el flujo de inversión las omite (gap, no inventado).")
    if capex["duplicados_excluidos"]:
        total_dup = round(sum(d["importe"] for d in capex["duplicados_excluidos"]), 2)
        advertencias.append(
            f"Capex deduplicado: {len(capex['duplicados_excluidos'])} activo(s) con el mismo "
            f"`codigo` en GMAO y en Finanzas-Inmovilizado por {total_dup} € se han contado UNA "
            "sola vez (con el importe contable de inmovilizado) para no duplicar la misma compra "
            "física en el flujo de inversión.")

    # ── Financiación ─────────────────────────────────────────────────────────────────
    delta_deuda_financiera = round(sum(_d(pc1, pc0, k) for k in _FIN_PASIVO_CORRIENTE)
                                  + sum(_d(pnc1, pnc0, k) for k in _FIN_PASIVO_NO_CORRIENTE), 2)
    delta_capital_y_aportaciones = round(sum(_d(fp1, fp0, k) for k in _FIN_FONDOS_PROPIOS), 2)
    dividendos_pagados = 0.0   # NO trackeado (ver auditoría punto 5) — no se inventa.
    flujo_financiacion = round(delta_deuda_financiera + delta_capital_y_aportaciones - dividendos_pagados, 2)
    advertencias.append("dividendos_pagados=0: ningún motor existente trackea reparto de dividendos "
                        "ni aportaciones de capital como tales (confirmado: sin tablas `dividendo`/"
                        "`reparto_beneficio`/`aportacion_capital`) — gap real, reportado, no inventado.")

    variacion_neta_calculada = round(flujo_explotacion + flujo_inversion + flujo_financiacion, 2)

    efectivo0, efectivo1 = ac0.get("efectivo", 0.0), ac1.get("efectivo", 0.0)
    variacion_neta_real = round(efectivo1 - efectivo0, 2)
    ajuste_conciliacion = round(variacion_neta_real - variacion_neta_calculada, 2)
    cuadra = abs(ajuste_conciliacion) < 0.01
    if not cuadra:
        logger.error(
            "generar_estado_flujos(%s, empresa=%s): NO CONCILIA con el efectivo real — "
            "calculado=%s real=%s ajuste=%s (posible movimiento de caja sin reflejo contable "
            "en el grupo correspondiente — p.ej. compra de inmovilizado pagada pero nunca "
            "contabilizada en grupo 2/cuenta 57x fuera del circuito habitual)",
            anio, id_empresa, variacion_neta_calculada, variacion_neta_real, ajuste_conciliacion)
        advertencias.append(f"La suma de los 3 flujos ({variacion_neta_calculada} €) no coincide con "
                            f"la variación real de efectivo ({variacion_neta_real} €): ajuste de "
                            f"{ajuste_conciliacion} € sin explicar — revisar asientos del periodo.")

    return {
        "anio": anio, "id_empresa": id_empresa,
        "explotacion": {"resultado_del_ejercicio": resultado, "amortizacion": amortizacion,
                        "variacion_capital_circulante": variacion_capital_circulante,
                        "total": flujo_explotacion},
        "inversion": {"capex_gmao": -capex_gmao, "capex_inmovilizado_finanzas": -capex_finanzas,
                     "venta_activos": venta_activos,
                     "variacion_inversiones_financieras_cp": -delta_inv_financieras_cp,
                     "capex_duplicados_excluidos": capex["duplicados_excluidos"],
                     "total": flujo_inversion},
        "financiacion": {"variacion_deuda_financiera": delta_deuda_financiera,
                        "variacion_capital_y_aportaciones": delta_capital_y_aportaciones,
                        "dividendos_pagados": -dividendos_pagados, "total": flujo_financiacion},
        "variacion_neta_calculada": variacion_neta_calculada,
        "variacion_neta_real_efectivo": variacion_neta_real,
        "efectivo_inicial": efectivo0, "efectivo_final": efectivo1,
        "ajuste_conciliacion": ajuste_conciliacion,
        "cuadra": cuadra, "advertencias": advertencias,
    }
