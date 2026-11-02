"""
Servicio integrador de FINIQUITO (RRHH Fase Finiquito) — orquestador impuro.

Reúne del empleado real (contrato vigente, datos fiscales, saldo de vacaciones, bolsa de horas)
todo lo necesario para `finiquito_motor.FiniquitoInput` y delega TODO el cálculo económico en
`finiquito_motor.calcular_finiquito` (que a su vez reutiliza `nomina_motor.calcular_nomina` para
la parte salarial/SS/IRPF) — este servicio NUNCA recalcula esa aritmética, solo la alimenta con
datos reales.

Validación explícita (mismo espíritu que la Fase F.2 de nómina — "ningún camino debe aplicar un
valor por defecto silencioso a un dato que en realidad falta"): cada prerrequisito (contrato,
salario/tarifa, IRPF, bolsa de horas si aplica) se comprueba ANTES de calcular; si falta, se lanza
`GestionFiniquitoError` con un mensaje claro de QUÉ falta y DÓNDE completarlo — mismo patrón que
`GestionLaboralError` (vacaciones/ausencias) y `GestionNominaError` (nómina).

Entitlement de vacaciones (decisión documentada de esta fase): se auditó `rrhh_contratos` y no
existe ningún campo de días de vacaciones/año (ni en el contrato ni en `jornada`) — no hace falta
ninguna migración nueva: se reutiliza tal cual `vacaciones_servicio.DIAS_ANUALES_DEFECTO` (30 días
naturales/año, mínimo legal español, Art. 38.1 ET), la MISMA constante que ya usa
`vacaciones_servicio.saldo()` en el resto del sistema — fuente única, sin duplicar el valor. El
saldo (días disfrutados/reservados del año) se reutiliza de `vacaciones_servicio.saldo()`, nunca
se recalculan sumando `rrhh_vacaciones` por cuenta propia; solo el DERECHO ANUAL generado se
prorratea aquí a los días realmente trabajados en el año (lo que `saldo()` no hace, porque asume
el año completo).

Pagas extra: sin ningún campo persistente en `rrhh_contratos` que indique si las pagas extra del
contrato están prorrateadas mensualmente o no (auditado; no existe), se asume por DEFECTO que SÍ
lo están — mismo valor por defecto que `NominaInput.pagas_extra_prorrateadas` en `nomina_motor` y
el escenario más habitual hoy en España — por lo que `importe_pagas_extra_pendientes` se calcula
a 0. El campo `imp_pagas` del formulario queda editable tras pulsar "Calcular": si el contrato
concreto NO prorratea las extras, el usuario introduce manualmente el importe pendiente (excepción
puntual, igual que el resto de campos de estos formularios).
"""

from __future__ import annotations

import datetime as _dt
import logging

from src.rrhh.finiquito_motor import FiniquitoInput, FiniquitoResultado, calcular_finiquito
from src.rrhh.nomina_servicio import num
from src.rrhh.parametros_cotizacion import cargar_parametros
from src.rrhh.vacaciones_servicio import DIAS_ANUALES_DEFECTO

logger = logging.getLogger("rrhh.finiquito_servicio")


class GestionFiniquitoError(Exception):
    """Prerrequisito de cálculo ausente: mensaje claro y accionable para el usuario."""


def _fecha(valor) -> "_dt.date | None":
    if valor is None:
        return None
    if isinstance(valor, _dt.datetime):
        return valor.date()
    if isinstance(valor, _dt.date):
        return valor
    s = str(valor).strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


def _dias_anio(anio: int) -> int:
    return (_dt.date(anio, 12, 31) - _dt.date(anio, 1, 1)).days + 1


def _horas_fichadas_periodo(emp: dict, f_efectos: _dt.date) -> float:
    """Horas REALMENTE fichadas por `emp` en el mes de `f_efectos` (modelo de pago por horas) —
    misma fuente que `nomina_servicio`/`NominaInlineForm` (`db.usuario.listar_fichajes_empleado`)."""
    id_usuario = emp.get("id_usuario")
    if not id_usuario:
        return 0.0
    try:
        from src.db.usuario import listar_fichajes_empleado
        fichajes = listar_fichajes_empleado(id_usuario, anio=f_efectos.year, mes=f_efectos.month) or []
        return round(sum(int(f.get("segundos") or 0) for f in fichajes) / 3600.0, 2)
    except Exception as e:
        logger.debug("finiquito: horas fichadas periodo (%s): %s", id_usuario, e)
        return 0.0


def construir_finiquito_input(id_empleado, id_empresa, fecha_efectos, pais: str = "ES"):
    """Reúne del empleado/contrato/datos fiscales/vacaciones/bolsa de horas todo lo necesario
    para `FiniquitoInput`, validando cada prerrequisito con un mensaje claro y accionable.
    Devuelve `(FiniquitoInput, ParametrosAnio)`. Lanza `GestionFiniquitoError` si falta algún
    dato imprescindible."""
    if not id_empleado:
        raise GestionFiniquitoError("Selecciona primero un empleado.")
    f_efectos = _fecha(fecha_efectos)
    if not f_efectos:
        raise GestionFiniquitoError(
            "Indica una fecha de efectos válida (DD/MM/AAAA) antes de calcular el finiquito.")

    from src.rrhh.db import empleados as _db_empleados
    emp = _db_empleados.obtener_empleado(id_empleado, id_empresa=id_empresa)
    if not emp:
        raise GestionFiniquitoError("No se encontró el expediente de este empleado.")

    from src.rrhh import maestros
    contrato = maestros.entidad_contrato(id_empleado, id_empresa) or {}
    if not contrato:
        raise GestionFiniquitoError(
            "No se encontró ningún contrato para este empleado. Date de alta su contrato en la "
            "pestaña 'Contratos' antes de generar el finiquito.")

    modelo_pago = str(contrato.get("modelo_pago") or "fijo").strip().lower()
    if modelo_pago == "hora":
        tarifa = num(contrato.get("tarifa_hora"))
        if not tarifa:
            raise GestionFiniquitoError(
                "Falta la tarifa por hora del contrato de este empleado. Complétala en la "
                "pestaña 'Contratos' (modelo de pago: por horas) antes de generar el finiquito.")
        horas = _horas_fichadas_periodo(emp, f_efectos)
        salario_base_mensual = round(horas * tarifa, 2)
    else:
        salario_contrato = num(contrato.get("salario"))
        salario_base_emp = num(emp.get("salario_base"))
        if salario_contrato:
            # `rrhh_contratos.salario` es BRUTO ANUAL (mismo criterio que `nomina_servicio`/
            # `NominaInlineForm._autollenar`, nunca un /12 fijo cuando hay nº de pagas explícito;
            # aquí se usa 12 por ser el reparto mensual estándar de la ficha de contrato).
            salario_base_mensual = round(salario_contrato / 12, 2)
        elif salario_base_emp:
            salario_base_mensual = salario_base_emp
        else:
            raise GestionFiniquitoError(
                "Falta el salario base de este empleado. Complétalo en su expediente o en su "
                "contrato antes de generar el finiquito.")

    from src.rrhh.db import datos_fiscales as _df
    df = _df.obtener_datos_fiscales(id_empleado, id_empresa)
    irpf_tipo = (float(df.get("irpf_pct_calculado"))
                if df and df.get("irpf_pct_calculado") is not None else None)
    if irpf_tipo is None:
        raise GestionFiniquitoError(
            "Falta el porcentaje de IRPF del empleado. Complétalo en la pestaña 'Modelo Fiscal "
            "Empleados' antes de generar el finiquito.")

    # ── Vacaciones no disfrutadas (Art. 38 ET; ver docstring del módulo) ────────────────────
    from src.rrhh.vacaciones_servicio import saldo as _saldo_vac
    anio = f_efectos.year
    fecha_alta = _fecha(emp.get("fecha_alta")) or _fecha(contrato.get("fecha_inicio"))
    inicio_computo = _dt.date(anio, 1, 1)
    if fecha_alta and fecha_alta.year == anio and fecha_alta > inicio_computo:
        inicio_computo = fecha_alta
    if f_efectos < inicio_computo:
        raise GestionFiniquitoError(
            "La fecha de efectos es anterior a la fecha de alta del empleado. Revisa la fecha "
            "de efectos antes de calcular el finiquito.")
    dias_trabajados_anio = max(0, (f_efectos - inicio_computo).days + 1)
    dias_generados = round(DIAS_ANUALES_DEFECTO * dias_trabajados_anio / _dias_anio(anio), 2)
    try:
        saldo_vac = _saldo_vac(id_empleado, anio=anio, id_empresa=id_empresa,
                               dias_anuales=DIAS_ANUALES_DEFECTO)
    except Exception as e:
        logger.error("finiquito: saldo de vacaciones de %s: %s", id_empleado, e)
        raise GestionFiniquitoError(
            "No se pudo calcular el saldo de vacaciones de este empleado.") from e
    dias_disfrutados = float(saldo_vac.get("disfrutados") or 0.0)
    dias_reservados = float(saldo_vac.get("pendientes") or 0.0)

    # ── Bolsa de horas pendiente de compensar por la EMPRESA (solo si el contrato la compensa
    # "en pago"; si no, no aplica — igual que `nomina_servicio._enriquecer_fase_f`). A diferencia
    # de la nómina mensual (donde es un enriquecimiento OPCIONAL que nunca debe frenar la nómina),
    # en el finiquito SÍ es un importe que se le debe al empleado: si el contrato lo activa pero
    # faltan datos para calcularlo (horas diarias sin definir, sin vigencia), se informa con
    # claridad en vez de omitirlo en silencio.
    importe_horas_bolsa = 0.0
    if str(contrato.get("bolsa_horas_compensacion") or "") == "pago":
        from src.rrhh import bolsa_horas as _bh
        try:
            res_bolsa = _bh.calcular_bolsa_horas_empleado(id_empleado, id_empresa=id_empresa)
        except ValueError as e:
            raise GestionFiniquitoError(
                f"No se pudo calcular la bolsa de horas de este empleado: {e} Complétala desde "
                "Horarios antes de generar el finiquito.") from e
        horas_pendientes = float(res_bolsa.get("horas_compensar_empresa") or 0.0)
        if horas_pendientes:
            tarifa_hora = num(contrato.get("tarifa_hora"))
            if not tarifa_hora:
                bolsa = _bh.obtener_bolsa_horas(id_empleado, id_empresa=id_empresa) or {}
                horas_diarias = num(bolsa.get("horas_diarias"))
                if horas_diarias:
                    # 21,75 = media de días laborables/mes en España — misma aproximación
                    # documentada que ya usa `nomina_servicio._enriquecer_fase_f`.
                    tarifa_hora = round(salario_base_mensual / (horas_diarias * 21.75), 4)
            importe_horas_bolsa = round(horas_pendientes * tarifa_hora, 2)

    modalidad = str(contrato.get("modalidad") or "").upper()
    tipo_contrato_ss = "temporal" if "TEMPORAL" in modalidad else "indefinido"

    entrada = FiniquitoInput(
        salario_base_mensual=salario_base_mensual,
        dias_trabajados_periodo=f_efectos.day,
        grupo_cotizacion=str(contrato.get("grupo_cotizacion") or "7"),
        tipo_contrato=tipo_contrato_ss,
        irpf_tipo=irpf_tipo,
        dias_vacaciones_generados=dias_generados,
        dias_vacaciones_disfrutados=dias_disfrutados,
        dias_vacaciones_reservados=dias_reservados,
        importe_pagas_extra_pendientes=0.0,   # ver docstring: se asume prorrateo mensual por defecto
        importe_horas_bolsa=importe_horas_bolsa,
    )
    parametros = cargar_parametros(anio, pais)
    return entrada, parametros


def calcular_finiquito_empleado(id_empleado, id_empresa, fecha_efectos,
                                pais: str = "ES") -> FiniquitoResultado:
    """Punto único: id_empleado + fecha de efectos → `FiniquitoResultado` (del motor puro).
    Lanza `GestionFiniquitoError` con un mensaje claro y accionable si falta algún prerrequisito."""
    entrada, parametros = construir_finiquito_input(id_empleado, id_empresa, fecha_efectos, pais=pais)
    return calcular_finiquito(entrada, parametros)


def _fecha_iso(f: "_dt.date | None") -> str | None:
    return f.isoformat() if f else None


def _conceptos_json(resultado: FiniquitoResultado) -> str:
    import json
    campos = ("dias_trabajados", "vac_generadas", "vac_disfrutadas", "vac_pendientes",
              "imp_salario_pendiente", "imp_vacaciones", "imp_pagas", "imp_horas_extras",
              "retencion_pct", "desc_ss_trabajador", "total_bruto", "total_liquido")
    return json.dumps({c: getattr(resultado, c) for c in campos}, ensure_ascii=False, default=str)


def calcular_y_guardar_borrador(id_empleado, id_empresa, fecha_efectos, pais: str = "ES"):
    """Punto único para la GUI (F.Finiquito — disciplina borrador/aprobada, mismo espíritu que
    `rrhh_nominas.estado`): calcula con el motor puro (`calcular_finiquito_empleado`, sin cambios)
    y PERSISTE el resultado en `rrhh_finiquitos` con `estado='borrador'` — el finiquito (documento
    legal) deja de vivir solo en memoria hasta que se genera el PDF.

    Recalcular (pulsar «Calcular» varias veces) actualiza el MISMO borrador vigente del empleado
    en vez de amontonar filas (`db.finiquitos.obtener_borrador_vigente`); si el último finiquito
    del empleado ya está 'aprobada', crea uno nuevo (nunca pisa un finiquito ya aprobado).

    Devuelve `(FiniquitoResultado, id_finiquito)`. `id_finiquito` es `None` si el cálculo fue bien
    pero la persistencia falló (no se lanza — un fallo de BD aquí no debe impedir ver el desglose
    calculado), pero la GUI debe avisar de que NO se guardó el borrador antes de permitir generar
    el PDF (ver `rrhh_finiquito_inline.py`)."""
    resultado = calcular_finiquito_empleado(id_empleado, id_empresa, fecha_efectos, pais=pais)

    from src.rrhh.db import finiquitos as _db_finiquitos
    f_efectos = _fecha(fecha_efectos)
    campos = {
        "fecha_efectos": _fecha_iso(f_efectos),
        "total_bruto": resultado.total_bruto,
        "total_liquido": resultado.total_liquido,
        "conceptos": _conceptos_json(resultado),
    }
    try:
        borrador = _db_finiquitos.obtener_borrador_vigente(id_empleado, id_empresa)
        if borrador:
            ok = _db_finiquitos.actualizar_finiquito(borrador["id"], id_empresa, **campos)
            id_finiquito = borrador["id"] if ok else None
        else:
            id_finiquito = _db_finiquitos.crear_finiquito(id_empleado, id_empresa, **campos)
    except Exception as e:
        logger.error("calcular_y_guardar_borrador: persistir borrador de %s: %s", id_empleado, e)
        id_finiquito = None
    return resultado, id_finiquito
