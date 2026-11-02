"""
Balance de Situación (Cuentas Anuales — pieza 1 de 3 de este módulo, junto a `ecpn.py` y
`estado_flujos.py`). Balance de situación abreviado PGC a una fecha de cierre (31/12 de
`anio`), construido con SALDOS REALES (ningún número estimado) reutilizando:

  - El mecanismo de saldo por cuenta de `cierre._saldos()` (E6.2/F2.1) — NO se reescribe la
    agregación SQL: se reutiliza tal cual para obtener {codigo_cuenta, tipo, saldo}.
  - `informes.perdidas_ganancias()` para el resultado del ejercicio (NO se recalcula el PyG).

Un matiz importante sobre el "punto en el tiempo" (documentado porque es la pieza más
delicada de esta reutilización): `cierre._saldos(id_empresa, anio)` agrega SOLO los
apuntes cuyo asiento tiene `anio=<anio>`. Gracias al propio diseño de `cierre.py` (la
apertura del ejercicio N se fecha `N-01-01` con `anio=N`), esto representa exactamente el
saldo "a 31/12 de N" MIENTRAS el ejercicio N no se haya cerrado formalmente todavía (caso
normal: las Cuentas Anuales se generan ANTES de ejecutar `cerrar_ejercicio_formal`, para
poder aprobarlas). Si el ejercicio N YA está cerrado formalmente, `_saldos(N)` devuelve casi
cero (el asiento de cierre, por diseño, salda TODAS las cuentas patrimoniales dentro del
propio `anio=N`) — en ese caso el saldo de cierre real de N se recupera leyendo el asiento
de APERTURA de N+1 (que invierte el cierre y por tanto reproduce exactamente esos saldos),
vía `_saldos_cierre_ejercicio()` más abajo.

Resultado del ejercicio vs. resultados de ejercicios anteriores: el plan de cuentas de este
proyecto NO tiene (todavía) una cuenta distinta para "resultados de ejercicios anteriores no
aplicados" (ni 120 "Remanente" ni 121) — la cuenta 129 agrega, vía el mecanismo de
apertura/cierre, el resultado de TODOS los ejercicios anteriores no aplicados (la Propuesta
de Aplicación del Resultado, que movería 129 a reservas/dividendos/remanente, es
responsabilidad de otro desarrollo en curso — ver auditoría en el informe de esta tarea).
Aquí se presentan como DOS líneas separadas sin inventar ninguna cuenta nueva:
  - "resultados_ejercicios_anteriores" = saldo de 129 en el asiento de APERTURA del propio
    `anio` (lo que 129 arrastraba al empezar el año — 0 en el primer ejercicio de la empresa).
  - "resultado_del_ejercicio" = el PyG REAL del año: `informes.perdidas_ganancias(anio)`
    mientras el ejercicio no tenga regularización todavía (caso normal: Cuentas Anuales
    generadas ANTES del cierre formal), o la línea 129 del propio asiento de regularización
    (dato real ya posteado) si el ejercicio ya se regularizó — ver `_resultado_ejercicio_real`,
    que evita así una limitación conocida de `perdidas_ganancias` en ejercicios ya cerrados
    (agrega por `anio` sin excluir la propia regularización, que neteó los grupos 6/7 a cero).
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.contabilidad import cierre as Ci
from src.services.contabilidad import cuentas as K
from src.services.contabilidad import informes as I

logger = logging.getLogger("contab.balance_situacion")

_TIPOS_BALANCE = ("activo", "pasivo", "pn")


def _empresa(id_empresa=None):
    # IOC v2 (Bloque III): misma resolución de empresa que el resto de `contabilidad/*`.
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


# ── Mapeo de cuentas PGC → secciones del balance (FUENTE ÚNICA de esta clasificación) ───────
#
# Formato de cada regla: (prefijo_codigo, seccion, subseccion). Se busca el prefijo MÁS
# LARGO que coincida (orden de longitud 4→1), igual que el matching de cuentas reales en un
# plan contable. Si ninguna regla coincide, se cae a un cajón "otros_<seccion>" derivado del
# campo `tipo` de `contab_cuentas` (nunca se deja fuera del total — se audita con un warning).
#
# ACTIVO
#   No corriente: intangible (20,280 resta) · material (21,22,23,281,282 resta) ·
#                 inversiones financieras largo plazo (24,25,26) · activo por impuesto
#                 diferido (474)
#   Corriente:    existencias (30-39) · deudores comerciales (43,44) · otros deudores /
#                 HP deudora (460,470,4700,472,544) · inversiones financieras corto
#                 plazo (54,56) · periodificaciones corto (480) · efectivo (57)
# PATRIMONIO NETO (PN)
#   capital (100-103) · reservas (110,111,112,113,114,115,117,118,119) ·
#   subvenciones/ajustes (130-137) · resultados anteriores y del ejercicio: 129 (tratado
#   aparte, ver docstring) · (acciones propias 108/109, resta)
# PASIVO
#   No corriente: provisiones largo (14) · deudas largo con entidades de crédito y otras
#                 (16,17,18) · pasivo por impuesto diferido (479)
#   Corriente:    provisiones corto (499,529) · deudas corto con entidades de crédito
#                 (51,52) · fianzas/otras deudas corto (55,56 pasivo) · proveedores y
#                 acreedores comerciales (400,401,403,405,406,41,465,466) · HP y SS
#                 acreedoras (475,4750,4751,476,477) · periodificaciones corto (485)
_REGLAS_ACTIVO = [
    ("280", "no_corriente", "amortizacion_intangible_resta"),
    ("281", "no_corriente", "amortizacion_material_resta"),
    ("282", "no_corriente", "amortizacion_inv_inmobiliarias_resta"),
    ("29", "no_corriente", "deterioro_resta"),
    ("20", "no_corriente", "inmovilizado_intangible"),
    ("21", "no_corriente", "inmovilizado_material"),
    ("22", "no_corriente", "inversiones_inmobiliarias"),
    ("23", "no_corriente", "inmovilizado_en_curso"),
    ("24", "no_corriente", "inversiones_financieras_largo_plazo"),
    ("25", "no_corriente", "inversiones_financieras_largo_plazo"),
    ("26", "no_corriente", "inversiones_financieras_largo_plazo"),
    ("474", "no_corriente", "activo_impuesto_diferido"),
    ("30", "corriente", "existencias"), ("31", "corriente", "existencias"),
    ("32", "corriente", "existencias"), ("33", "corriente", "existencias"),
    ("34", "corriente", "existencias"), ("35", "corriente", "existencias"),
    ("36", "corriente", "existencias"), ("39", "corriente", "existencias"),
    ("430", "corriente", "deudores_comerciales"), ("431", "corriente", "deudores_comerciales"),
    ("435", "corriente", "deudores_comerciales"), ("436", "corriente", "deudores_comerciales"),
    ("440", "corriente", "otros_deudores"), ("460", "corriente", "otros_deudores"),
    ("544", "corriente", "inversiones_financieras_corto_plazo"),
    ("4700", "corriente", "hp_deudora"), ("470", "corriente", "hp_deudora"),
    ("472", "corriente", "hp_deudora"),
    ("54", "corriente", "inversiones_financieras_corto_plazo"),
    ("56", "corriente", "inversiones_financieras_corto_plazo"),
    ("480", "corriente", "periodificaciones"),
    ("57", "corriente", "efectivo"),
]
_REGLAS_PASIVO = [
    ("14", "no_corriente", "provisiones"),
    ("16", "no_corriente", "deudas_grupo_largo_plazo"),
    ("17", "no_corriente", "deudas_financieras_largo_plazo"),
    ("18", "no_corriente", "deudas_largo_plazo_otras"),
    ("479", "no_corriente", "pasivo_impuesto_diferido"),
    ("499", "corriente", "provisiones"), ("529", "corriente", "provisiones"),
    ("51", "corriente", "deudas_grupo_corto_plazo"),
    ("520", "corriente", "deudas_financieras_corto_plazo"),
    ("521", "corriente", "deudas_financieras_corto_plazo"),
    ("522", "corriente", "deudas_financieras_corto_plazo"),
    ("527", "corriente", "deudas_financieras_corto_plazo"),
    ("400", "corriente", "acreedores_comerciales"), ("401", "corriente", "acreedores_comerciales"),
    ("403", "corriente", "acreedores_comerciales"), ("405", "corriente", "acreedores_comerciales"),
    ("406", "corriente", "acreedores_comerciales"), ("41", "corriente", "acreedores_comerciales"),
    ("465", "corriente", "acreedores_comerciales"), ("466", "corriente", "acreedores_comerciales"),
    ("4750", "corriente", "hp_ss_acreedoras"), ("4751", "corriente", "hp_ss_acreedoras"),
    ("475", "corriente", "hp_ss_acreedoras"), ("476", "corriente", "hp_ss_acreedoras"),
    ("477", "corriente", "hp_ss_acreedoras"),
    ("485", "corriente", "periodificaciones"),
    ("55", "corriente", "otras_deudas"), ("56", "corriente", "otras_deudas"),
]
_REGLAS_PN = [
    ("108", "fondos_propios", "acciones_propias_resta"),
    ("109", "fondos_propios", "acciones_propias_resta"),
    ("100", "fondos_propios", "capital"), ("101", "fondos_propios", "capital"),
    ("102", "fondos_propios", "capital"), ("103", "fondos_propios", "capital"),
    ("110", "fondos_propios", "prima_emision"),
    ("111", "fondos_propios", "otros_instrumentos_patrimonio"),
    ("118", "fondos_propios", "otras_aportaciones_socios"),
    ("112", "fondos_propios", "reservas"), ("113", "fondos_propios", "reservas"),
    ("114", "fondos_propios", "reservas"), ("115", "fondos_propios", "reservas"),
    ("117", "fondos_propios", "reservas"), ("119", "fondos_propios", "reservas"),
    ("129", "fondos_propios", "resultado_129"),      # tratado aparte, ver docstring
    ("13", "ajustes_y_subvenciones", "subvenciones_y_ajustes"),
]

# Códigos EXCLUIDOS del bucket genérico de PN (129 se trata aparte explícitamente).
_CODIGO_RESULTADO = "129"


def _match(codigo, reglas):
    cod = str(codigo)
    for longitud in (4, 3, 2):
        pref = cod[:longitud]
        for p, seccion, sub in reglas:
            if p == pref:
                return seccion, sub
    return None


def _clasificar(codigo, tipo):
    """(seccion, subseccion) para una cuenta, según su `tipo` (activo/pasivo/pn) + prefijo.
    Nunca devuelve None para activo/pasivo/pn: cae a un cajón "otros_<tipo>_<seccion>" si
    ninguna regla de prefijo coincide (se audita con warning, nunca se pierde el importe)."""
    if tipo == "activo":
        m = _match(codigo, _REGLAS_ACTIVO)
        if m:
            return m
        logger.warning("balance: cuenta activo %s sin regla de prefijo — cajón genérico", codigo)
        return "corriente", "otros_activo_corriente"
    if tipo == "pasivo":
        m = _match(codigo, _REGLAS_PASIVO)
        if m:
            return m
        logger.warning("balance: cuenta pasivo %s sin regla de prefijo — cajón genérico", codigo)
        return "corriente", "otras_deudas"
    if tipo == "pn":
        m = _match(codigo, _REGLAS_PN)
        if m:
            return m
        logger.warning("balance: cuenta PN %s sin regla de prefijo — cajón genérico", codigo)
        return "fondos_propios", "otros_fondos_propios"
    return None


def _saldos_cierre_ejercicio(id_empresa, anio) -> list[dict]:
    """Saldo por cuenta (activo/pasivo/pn) "a 31/12 de `anio`", resuelto correctamente tanto
    si el ejercicio sigue abierto (caso normal al generar Cuentas Anuales) como si YA se
    cerró formalmente (ver docstring del módulo): en ese caso se recupera leyendo el asiento
    de apertura del ejercicio siguiente, que reproduce exactamente esos saldos de cierre."""
    anio = int(anio)
    if K.ejercicio_cerrado(anio, id_empresa):
        apertura = Ci.buscar_asiento(id_empresa, anio + 1, "apertura")
        if apertura:
            from src.services.contabilidad.asientos import obtener_asiento
            det = obtener_asiento(apertura["id"], id_empresa) or {}
            out = []
            with obtener_conexion() as conn, conn.cursor() as cur:
                for ap in det.get("apuntes", []):
                    cur.execute("SELECT tipo FROM contab_cuentas WHERE id_empresa=%s AND codigo=%s",
                                (id_empresa, ap["codigo_cuenta"]))
                    r = cur.fetchone()
                    tipo = (r[0] if r and not isinstance(r, dict) else (r.get("tipo") if r else None)) or "otro"
                    if tipo not in _TIPOS_BALANCE:
                        continue
                    saldo = round(float(ap["debe"] or 0) - float(ap["haber"] or 0), 2)
                    if abs(saldo) > 0.005:
                        out.append({"codigo": ap["codigo_cuenta"], "tipo": tipo, "saldo": saldo})
            return out
        logger.warning("balance: ejercicio %s cerrado pero sin apertura %s — uso saldo en bruto "
                       "(puede no representar el cierre si abrir_siguiente=False)", anio, anio + 1)
    return Ci._saldos(id_empresa, anio, solo_tipos=_TIPOS_BALANCE)


def _resultado_ejercicio_real(id_empresa, anio) -> float:
    """Resultado del ejercicio REALMENTE contabilizado. Si el ejercicio ya tiene asiento de
    regularización (normal/cierre_formal YA ejecutado), se lee DIRECTAMENTE su línea 129 —
    dato real ya posteado, y la única forma fiable de recuperarlo: `informes.
    perdidas_ganancias(anio)` agrega por `a.anio` SIN excluir el propio asiento de
    regularización, que ya neteó los grupos 6/7 a cero dentro de ese mismo `anio` — así que
    tras regularizar, `perdidas_ganancias(anio)` devuelve 0 (limitación conocida del motor de
    PyG reutilizado, documentada, no parcheada aquí). Si NO hay regularización todavía (caso
    normal: Cuentas Anuales generadas ANTES del cierre formal, para poder aprobarlas), se usa
    `perdidas_ganancias(anio)` tal cual — el PyG real, aún no posteado a 129."""
    reg = Ci.buscar_asiento(id_empresa, anio, "regularizacion")
    if reg:
        from src.services.contabilidad.asientos import obtener_asiento
        det = obtener_asiento(reg["id"], id_empresa) or {}
        for ap in det.get("apuntes", []):
            if ap["codigo_cuenta"] == _CODIGO_RESULTADO:
                return round(float(ap["haber"] or 0) - float(ap["debe"] or 0), 2)
    return round(I.perdidas_ganancias(id_empresa, anio=anio).get("resultado", 0.0), 2)


def _saldo_129_apertura(id_empresa, anio) -> float:
    """Lo que 129 arrastraba AL EMPEZAR `anio` (resultados de ejercicios anteriores no
    aplicados) — 0 en el primer ejercicio de la empresa (sin apertura previa)."""
    apertura = Ci.buscar_asiento(id_empresa, anio, "apertura")
    if not apertura:
        return 0.0
    from src.services.contabilidad.asientos import obtener_asiento
    det = obtener_asiento(apertura["id"], id_empresa) or {}
    saldo = 0.0
    for ap in det.get("apuntes", []):
        if ap["codigo_cuenta"] == _CODIGO_RESULTADO:
            saldo += float(ap["debe"] or 0) - float(ap["haber"] or 0)
    return round(-saldo, 2)   # 129 es PN/acreedora: se invierte, igual que el resto de PN


def generar_balance(anio, id_empresa=None) -> dict:
    """Balance de situación abreviado a 31/12 de `anio`. Estructura:
    {activo: {no_corriente:{...líneas,total}, corriente:{...,total}, total},
     pn_pasivo: {patrimonio_neto:{...,total}, pasivo_no_corriente:{...,total},
                 pasivo_corriente:{...,total}, total},
     cuadra: bool, diferencia: float, resultado_del_ejercicio, resultados_ejercicios_anteriores,
     advertencias: [...]}
    Consistencia Activo==PN+Pasivo SIEMPRE comprobada; una descuadre se LOGUEA como error
    (nunca se oculta) — indicaría un fallo real de doble partida aguas arriba."""
    id_empresa = _empresa(id_empresa)
    anio = int(anio)
    advertencias = []
    filas = _saldos_cierre_ejercicio(id_empresa, anio)

    activo = {"no_corriente": {}, "corriente": {}}
    pasivo = {"no_corriente": {}, "corriente": {}}
    pn = {"fondos_propios": {}, "ajustes_y_subvenciones": {}}

    for f in filas:
        codigo, tipo, saldo = f["codigo"], f["tipo"], f["saldo"]
        if tipo == "pn" and codigo == _CODIGO_RESULTADO:
            continue   # 129 se trata aparte (resultado_del_ejercicio + resultados_anteriores)
        clasif = _clasificar(codigo, tipo)
        if not clasif:
            continue
        seccion, sub = clasif
        destino = activo if tipo == "activo" else (pasivo if tipo == "pasivo" else pn)
        bucket = destino[seccion]
        # Convención debe-haber: `saldo` = debe-haber. Para tipo='activo' (naturaleza deudora)
        # el saldo natural ya es positivo, y las cuentas "resta" (280/281/282/29x, amortización
        # acumulada/deterioro — naturaleza ACREEDORA pero tipo='activo', ver plan_pgc.py) tienen
        # saldo NEGATIVO de forma natural, así que sumarlo tal cual ya minora correctamente la
        # sección — no se invierte signo para activo. Para pasivo/pn (naturaleza acreedora), el
        # saldo natural es NEGATIVO para un importe real de pasivo/PN — se invierte el signo
        # (mismo criterio que `informes.balance_situacion`: `-t.get('pasivo')`/`-t.get('pn')`).
        valor = saldo if tipo == "activo" else -saldo
        bucket[sub] = round(bucket.get(sub, 0.0) + valor, 2)

    resultado_ejercicio = _resultado_ejercicio_real(id_empresa, anio)
    resultados_anteriores = _saldo_129_apertura(id_empresa, anio)
    pn["fondos_propios"]["resultado_del_ejercicio"] = round(resultado_ejercicio, 2)
    pn["fondos_propios"]["resultados_ejercicios_anteriores"] = resultados_anteriores

    def _total(d):
        return round(sum(d.values()), 2)

    act_nc_total = _total(activo["no_corriente"])
    act_c_total = _total(activo["corriente"])
    activo_total = round(act_nc_total + act_c_total, 2)

    pn_total = round(_total(pn["fondos_propios"]) + _total(pn["ajustes_y_subvenciones"]), 2)
    pas_nc_total = _total(pasivo["no_corriente"])
    pas_c_total = _total(pasivo["corriente"])
    pn_pasivo_total = round(pn_total + pas_nc_total + pas_c_total, 2)

    diferencia = round(activo_total - pn_pasivo_total, 2)
    cuadra = abs(diferencia) < 0.01
    if not cuadra:
        logger.error("generar_balance(%s, empresa=%s): NO CUADRA — activo=%s pn_pasivo=%s "
                     "diferencia=%s (posible fallo de doble partida aguas arriba, revisar)",
                     anio, id_empresa, activo_total, pn_pasivo_total, diferencia)
        advertencias.append(f"El balance NO cuadra: diferencia de {diferencia} € — revisar asientos.")

    return {
        "anio": anio, "id_empresa": id_empresa,
        "activo": {"no_corriente": {**activo["no_corriente"], "total": act_nc_total},
                   "corriente": {**activo["corriente"], "total": act_c_total},
                   "total": activo_total},
        "pn_pasivo": {
            "patrimonio_neto": {"fondos_propios": {**pn["fondos_propios"], "total": _total(pn["fondos_propios"])},
                                "ajustes_y_subvenciones": {**pn["ajustes_y_subvenciones"],
                                                           "total": _total(pn["ajustes_y_subvenciones"])},
                                "total": pn_total},
            "pasivo_no_corriente": {**pasivo["no_corriente"], "total": pas_nc_total},
            "pasivo_corriente": {**pasivo["corriente"], "total": pas_c_total},
            "total": pn_pasivo_total},
        "resultado_del_ejercicio": round(resultado_ejercicio, 2),
        "resultados_ejercicios_anteriores": resultados_anteriores,
        "cuadra": cuadra, "diferencia": diferencia, "advertencias": advertencias,
    }
