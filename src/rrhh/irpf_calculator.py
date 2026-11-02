"""
Servicio: CÁLCULO DE IRPF (Modelo 145 AEAT) — Fase B2 del plan de RRHH/nómina.

Implementa el "procedimiento general de cálculo de retenciones" del RIRPF (arts. 80-87, mínimo
personal y familiar de los arts. 57-61 LIRPF): mínimo personal + incremento por situación familiar +
mínimo por descendientes/ascendientes/discapacidad, cuota de retención POR DIFERENCIA entre aplicar
la escala general a la retribución (menos reducciones) y al mínimo personal y familiar, tipo previo
= cuota / retribución íntegra, y minoración final por vivienda habitual (adquisición pre-2013).

Los tramos/importes del año fiscal viven en `assets/rrhh/irpf_es.json` (fuente única, versionable —
NUNCA hardcodeados aquí), mismo patrón que `assets/rrhh/cotizacion_es.json` +
`src/rrhh/parametros_cotizacion.py` para los parámetros de cotización a la Seguridad Social.

`calcular_tipo_irpf(...)` es una función PURA (sin BD, sin Qt) — testeable de forma aislada.
`IRPFCalculatorService` es la capa fina que orquesta: lee `rrhh_datos_fiscales` (`db.datos_fiscales`)
+ la retribución bruta anual prevista (reutilizando `src.rrhh.maestros.entidad_contrato`, no se
re-consulta crudo) y persiste el resultado en `rrhh_datos_fiscales.irpf_pct_calculado` — el ÚNICO
campo que la nómina consulta automáticamente (Fase F, fuera del alcance de esta fase).

Honestidad del cálculo (documentada explícitamente, no oculta en el código): el checkbox
"irregularidad de rentas" del Modelo 145 no lleva un importe propio en el formulario oficial (la
comunicación al pagador es un SÍ/NO, no una cantidad) — por eso NO se inventa una base sobre la que
aplicar la reducción del 30% del art. 18.2 LIRPF; el aviso se conserva en el desglose devuelto
(`aviso_rentas_irregulares`) para que el PDF/la GUI lo muestren, pero no altera el tipo calculado.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger("rrhh.irpf_calculator")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Códigos internos normalizados (usados por la GUI, la BD y este cálculo — mismo valor en los tres).
SITUACIONES_FAMILIARES = ("1", "2", "3")
GRADOS_DISCAPACIDAD = ("ninguna", "menor_33", "entre_33_65", "mayor_65")


class IRPFCalculatorError(Exception):
    """Parámetros IRPF ausentes/corruptos, o datos fiscales del empleado insuficientes."""


# ── Carga de parámetros del ejercicio (assets/rrhh/irpf_es.json) ──────────────
def _ruta_parametros(pais: str = "ES") -> str:
    nombre = f"irpf_{pais.lower()}.json"
    try:
        from src.utils import recursos
        return recursos.ruta_recurso("assets", "rrhh", nombre)
    except Exception:
        return os.path.join(_ROOT, "assets", "rrhh", nombre)


_REQUERIDOS = ("minimo_contribuyente", "minimo_descendientes_tramos", "minimo_ascendiente",
              "discapacidad", "escala_general_retenciones", "tipo_maximo_pct")


def _validar_parametros(p: dict, clave: str):
    faltan = [k for k in _REQUERIDOS if k not in p]
    if faltan:
        raise IRPFCalculatorError(f"Parámetros IRPF incompletos en ejercicio {clave}: faltan {faltan}")
    if not isinstance(p.get("escala_general_retenciones"), list) or not p["escala_general_retenciones"]:
        raise IRPFCalculatorError(f"Escala general de retenciones vacía/incompleta en ejercicio {clave}")
    if not isinstance(p.get("discapacidad"), dict):
        raise IRPFCalculatorError(f"Bloque 'discapacidad' inválido en ejercicio {clave}")


def cargar_parametros_irpf(anio: int, pais: str = "ES") -> dict:
    """Parámetros del ejercicio `anio` (último disponible si no existe el exacto). Carga robusta:
    fichero ausente/corrupto/incompleto lanza `IRPFCalculatorError` — nunca produce un % silencioso
    a partir de datos rotos."""
    ruta = _ruta_parametros(pais)
    if not os.path.exists(ruta):
        raise IRPFCalculatorError(f"Recurso de parámetros IRPF no encontrado: {ruta}")
    try:
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise IRPFCalculatorError(f"Recurso de parámetros IRPF corrupto ({ruta}): {e}") from e
    if not isinstance(data, dict):
        raise IRPFCalculatorError(f"Recurso de parámetros IRPF con formato inválido: {ruta}")
    ejercicios = {k: v for k, v in data.items() if k.isdigit() and isinstance(v, dict)}
    if not ejercicios:
        raise IRPFCalculatorError(f"Sin ejercicios válidos en {ruta}")
    clave = str(anio) if str(anio) in ejercicios else max(ejercicios, key=int)
    if clave != str(anio):
        logger.info("Parámetros IRPF %s no encontrados; usando %s (último disponible).", anio, clave)
    p = ejercicios[clave]
    _validar_parametros(p, clave)
    return p


# ── Utilidades numéricas ────────────────────────────────────────────────────────
def _num(v, default: float = 0.0) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _cuota_por_escala(base: float, escala: list) -> float:
    """Cuota íntegra aplicando la escala general POR TRAMOS PROGRESIVOS (cada tramo tributa solo la
    porción de base que le corresponde, nunca el total al tipo marginal más alto)."""
    base = max(0.0, _num(base))
    cuota = 0.0
    limite_anterior = 0.0
    for tramo in escala:
        hasta = tramo.get("hasta")
        tipo = _num(tramo.get("tipo"))
        techo = _num(hasta) if hasta is not None else float("inf")
        if base <= limite_anterior:
            break
        parte = min(base, techo) - limite_anterior
        if parte > 0:
            cuota += parte * tipo / 100.0
        if base <= techo:
            break
        limite_anterior = techo
    return cuota


def _incremento_discapacidad(grado, params_disc: dict, incluir_ayuda: bool = False) -> float:
    grado = (grado or "ninguna").strip().lower()
    inc = 0.0
    if grado == "entre_33_65":
        inc = _num(params_disc.get("incremento_33_65"))
    elif grado == "mayor_65":
        inc = _num(params_disc.get("incremento_65_mas"))
    if incluir_ayuda and grado in ("entre_33_65", "mayor_65"):
        inc += _num(params_disc.get("incremento_ayuda_terceros_movilidad"))
    return inc


# ── Función PURA de cálculo (sin BD, sin Qt) ────────────────────────────────────
def calcular_tipo_irpf(datos_fiscales: dict, retribucion_bruta_anual: float, parametros: dict,
                       anio_actual: int | None = None) -> dict:
    """Procedimiento general de cálculo de retenciones del RIRPF.

    `datos_fiscales`: fila de `rrhh_datos_fiscales` con `hijos`/`ascendientes` embebidos (formato de
    `src.rrhh.db.datos_fiscales.obtener_datos_fiscales`).
    `retribucion_bruta_anual`: retribución total anual prevista (salario + complementos + pagas).
    `parametros`: dict de `cargar_parametros_irpf(anio)`.

    Devuelve el desglose COMPLETO (nunca solo el número final) para poder auditar/imprimir el
    cálculo, con `tipo_irpf_pct` como resultado a persistir."""
    anio_actual = anio_actual or datetime.now().year
    df = datos_fiscales or {}
    hijos = df.get("hijos") or []
    ascendientes = df.get("ascendientes") or []
    escala = parametros["escala_general_retenciones"]
    disc_p = parametros.get("discapacidad", {})

    retribucion = max(0.0, _num(retribucion_bruta_anual))

    # ── 1) Reducciones sobre la retribución (gasto genérico + movilidad geográfica + pensión
    #        compensatoria + anualidades por alimentos, todas de aplicación directa sobre la base) ──
    gasto_generico = _num(parametros.get("gasto_generico_anual"))
    gasto_movilidad = (_num(parametros.get("gasto_movilidad_geografica_anual"))
                       if df.get("movilidad_geografica") else 0.0)
    pension_comp = _num(df.get("pension_compensatoria_anual"))
    anualidades_alim = _num(df.get("anualidades_alimentos_anual"))
    base_tipo = max(0.0, retribucion - gasto_generico - gasto_movilidad
                    - pension_comp - anualidades_alim)

    # ── 2) Mínimo personal y familiar ────────────────────────────────────────────
    situacion = str(df.get("situacion_familiar") or "3")
    minimo = _num(parametros.get("minimo_contribuyente"))
    ajuste_situacion = 0.0
    if situacion == "2":
        ajuste_situacion = _num(parametros.get("incremento_situacion_2_conyuge_sin_rentas"))
    elif situacion == "1" and hijos:
        ajuste_situacion = _num(parametros.get("reduccion_situacion_1_monoparental"))
    minimo += ajuste_situacion

    tramos_hijos = parametros.get("minimo_descendientes_tramos") or []
    inc_menor3 = _num(parametros.get("incremento_descendiente_menor_3_anios"))
    edad_max_desc = int(parametros.get("edad_maxima_descendiente_computable", 25))
    computo_compartido_pct = _num(parametros.get("computo_hijo_compartido_pct"), 0.5)
    minimo_descendientes = 0.0
    n_hijo_computable = 0
    for h in hijos:
        anio_nac = h.get("anio_nacimiento")
        if anio_nac is None:
            continue
        edad = anio_actual - int(anio_nac)
        grado = h.get("grado_discapacidad")
        con_discapacidad = grado and grado != "ninguna"
        if edad < 0 or (edad > edad_max_desc and not con_discapacidad):
            continue   # fuera de edad computable (sin límite de edad si el descendiente es discapacitado)
        n_hijo_computable += 1
        idx = min(n_hijo_computable, len(tramos_hijos)) - 1
        importe_hijo = _num(tramos_hijos[idx]) if idx >= 0 else 0.0
        if edad < 3:
            importe_hijo += inc_menor3
        importe_hijo += _incremento_discapacidad(grado, disc_p)
        if not h.get("computo_entero"):
            importe_hijo *= computo_compartido_pct   # guarda y custodia compartida → 50% por defecto
        minimo_descendientes += importe_hijo
    minimo += minimo_descendientes

    edad_min_asc = int(parametros.get("edad_minima_ascendiente", 65))
    edad_inc_asc = int(parametros.get("edad_incremento_ascendiente", 75))
    factor_convivencia = _num(parametros.get("factor_convivencia_ascendiente_compartida"), 0.5)
    minimo_ascendientes = 0.0
    for a in ascendientes:
        anio_nac = a.get("anio_nacimiento")
        if anio_nac is None:
            continue
        edad = anio_actual - int(anio_nac)
        grado = a.get("grado_discapacidad")
        con_discapacidad = grado and grado != "ninguna"
        if edad < edad_min_asc and not con_discapacidad:
            continue
        importe_asc = _num(parametros.get("minimo_ascendiente"))
        if edad >= edad_inc_asc:
            importe_asc += _num(parametros.get("incremento_ascendiente_mayor_75_anios"))
        importe_asc += _incremento_discapacidad(grado, disc_p)
        if a.get("convivencia_otros_descendientes"):
            # Convive con otros descendientes con igual/mejor derecho → se prorratea (aproximación:
            # factor fijo configurable, no se modela el nº exacto de declarantes concurrentes).
            importe_asc *= factor_convivencia
        minimo_ascendientes += importe_asc
    minimo += minimo_ascendientes

    grado_trab = df.get("discapacidad_trabajador")
    incluir_ayuda = bool(df.get("ayuda_terceros_movilidad"))
    minimo_discapacidad_trabajador = _incremento_discapacidad(grado_trab, disc_p, incluir_ayuda=incluir_ayuda)
    minimo += minimo_discapacidad_trabajador

    # ── 3) Cuota de retención = cuota(base_tipo) − cuota(mínimo) [el mínimo tributa a tipo 0] ──────
    cuota_base = _cuota_por_escala(base_tipo, escala)
    cuota_minimo = _cuota_por_escala(minimo, escala)
    cuota_retencion = max(0.0, cuota_base - cuota_minimo)

    # ── 4) Tipo previo de retención = cuota de retención / retribución total íntegra ────────────────
    tipo_previo = (cuota_retencion / retribucion * 100.0) if retribucion > 0 else 0.0

    # ── 5) Minoración por deducción de vivienda habitual (adquisición/rehabilitación pre-2013,
    #        DT 18ª LIRPF): reduce el TIPO (no la base), solo si la retribución no excede el límite. ──
    viv = parametros.get("vivienda_pre2013", {})
    minoracion_vivienda = 0.0
    if df.get("vivienda_habitual_pre2013") and retribucion <= _num(
            viv.get("limite_retribucion_anual"), float("inf")):
        minoracion_vivienda = _num(viv.get("puntos_reduccion_tipo"))

    tipo_final = tipo_previo - minoracion_vivienda
    tipo_min = _num(parametros.get("tipo_minimo_pct"), 0.0)
    tipo_max = _num(parametros.get("tipo_maximo_pct"), 47.0)
    tipo_final = max(tipo_min, min(tipo_max, tipo_final))

    return {
        "retribucion_bruta_anual": round(retribucion, 2),
        "base_calculo_tipo": round(base_tipo, 2),
        "minimo_personal_familiar": round(minimo, 2),
        "minimo_descendientes": round(minimo_descendientes, 2),
        "minimo_ascendientes": round(minimo_ascendientes, 2),
        "minimo_discapacidad_trabajador": round(minimo_discapacidad_trabajador, 2),
        "cuota_base": round(cuota_base, 2),
        "cuota_minimo": round(cuota_minimo, 2),
        "cuota_retencion": round(cuota_retencion, 2),
        "tipo_previo_pct": round(tipo_previo, 2),
        "minoracion_vivienda_pct": round(minoracion_vivienda, 2),
        "tipo_irpf_pct": round(tipo_final, 2),
        "anio": anio_actual,
        "aviso_rentas_irregulares": bool(df.get("rentas_irregulares")),
    }


# ── Orquestación (BD + maestros) ────────────────────────────────────────────────
class IRPFCalculatorService:
    """Calcula y persiste el % de IRPF de un empleado. Capa fina: toda la aritmética real vive en
    `calcular_tipo_irpf` (función pura, testeable sin BD)."""

    def __init__(self, pais: str = "ES"):
        self._pais = pais

    def retribucion_bruta_anual_prevista(self, id_empleado, id_empresa=None) -> float:
        """Retribución bruta anual prevista (salario + complementos + pagas ya incluidas). Prioriza
        el contrato vigente (`rrhh_contratos.salario` — capturado como bruto ANUAL, ver la etiqueta
        "Salario bruto anual (€)" de `ContratoInlineForm`) reutilizando `src.rrhh.maestros`
        (no se re-consulta la tabla cruda); si no hay contrato, usa `rrhh_empleados.salario_base`
        (mensual) × 12."""
        contrato = {}
        try:
            from src.rrhh import maestros
            contrato = maestros.entidad_contrato(id_empleado, id_empresa) or {}
        except Exception as e:
            logger.debug("retribucion_bruta_anual_prevista/contrato(%s): %s", id_empleado, e)
        if contrato.get("salario"):
            return _num(contrato.get("salario"))
        emp = {}
        try:
            from src.rrhh.db import empleados
            emp = empleados.obtener_empleado(id_empleado, id_empresa) or {}
        except Exception as e:
            logger.debug("retribucion_bruta_anual_prevista/empleado(%s): %s", id_empleado, e)
        return _num(emp.get("salario_base")) * 12.0

    def calcular(self, id_empleado, id_empresa=None, anio: int | None = None,
                persistir: bool = True) -> dict:
        """Calcula el % de IRPF del empleado (procedimiento general RIRPF) y, si `persistir`, lo
        guarda en `rrhh_datos_fiscales.irpf_pct_calculado` + `fecha_calculo`. Requiere que el
        empleado ya tenga datos fiscales guardados (`Guardar Datos Fiscales` en la pestaña Modelo
        145) — lanza `IRPFCalculatorError` si no los tiene. Devuelve el desglose completo."""
        from src.rrhh.db import datos_fiscales as DF
        anio = anio or datetime.now().year
        df = DF.obtener_datos_fiscales(id_empleado, id_empresa)
        if df is None:
            raise IRPFCalculatorError(
                "El empleado no tiene datos fiscales guardados (Modelo 145). Guarda el formulario "
                "antes de calcular el IRPF.")
        retribucion = self.retribucion_bruta_anual_prevista(id_empleado, id_empresa)
        parametros = cargar_parametros_irpf(anio, self._pais)
        resultado = calcular_tipo_irpf(df, retribucion, parametros, anio_actual=anio)
        if persistir:
            DF.actualizar_irpf_calculado(id_empleado, id_empresa, pct=resultado["tipo_irpf_pct"])
        return resultado
