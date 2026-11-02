"""
Servicio integrador de nómina (F4.3.4) — único punto de orquestación.

Construye `NominaInput` desde `self._datos` (formulario), carga los parámetros legales
del ejercicio y delega TODO el cálculo en `nomina_motor.calcular_nomina`. Lo consumen
EXCLUSIVAMENTE `render_nomina` (formatea) y `persistencia` (guarda): ninguno recalcula.

Decisión sobre el campo salario (auditoría F4.3.0/F4.3.4): el formulario etiqueta
"Salario base mensual"; se interpreta como tal → `salario_base_mensual = salario` SIN
dividir por nº de pagas. Se elimina la división histórica `salario/num_pagas` (que
contradecía la etiqueta). El nº de pagas solo rige el prorrateo de extras dentro del
motor. La adaptación vive AQUÍ (no en el motor puro). `ss_pct` manual ya no se usa:
la SS se calcula por contingencias en el motor.
"""

import calendar as _calendar
import datetime as _dt
import json
import logging

from src.rrhh.nomina_motor import NominaInput, calcular_nomina
from src.rrhh.parametros_cotizacion import cargar_parametros

logger = logging.getLogger("rrhh.nomina_servicio")


class GestionNominaError(Exception):
    """Prerrequisito de cálculo ausente (contrato/salario/tarifa/IRPF): mensaje claro y
    accionable para el usuario, en vez de dejar que un dato ausente propague una excepción
    críptica (`TypeError`/`AttributeError`/división por cero) más abajo en el motor. Mismo
    patrón que `GestionLaboralError` (vacaciones/ausencias)."""

_MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def num(valor) -> float:
    """Parsea importes en formato europeo o simple ('1.200,50' / '1200.00' / '1200')."""
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return round(float(valor), 2)
    s = str(valor).strip()
    if not s:
        return 0.0
    try:
        if "," in s and "." in s:          # 1.200,50 → europeo
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:                      # 1200,50
            s = s.replace(",", ".")
        return round(float(s), 2)
    except ValueError:
        return 0.0


def _num_o_none(valor):
    if valor is None or str(valor).strip() == "":
        return None
    return num(valor)


def _anio(datos) -> int:
    f = datos.get("fecha")
    try:
        return _dt.datetime.strptime(str(f).strip(), "%d/%m/%Y").year
    except Exception:
        return _dt.date.today().year


def _resolver_periodo(datos: dict) -> tuple[int, int]:
    """(anio, mes) del periodo liquidado. Prioriza `periodo_anio`/`periodo_mes` (campos del
    formulario inline de Nóminas — F4.3.4); si no son parseables, cae a `fecha` (DD/MM/AAAA,
    compatibilidad con el wizard antiguo/el job automático); si tampoco, usa hoy. Necesario
    para la Fase F (IT/bolsa de horas), que necesita saber EXACTAMENTE qué mes se liquida —
    algo que el formulario inline nunca expuso con un único campo "fecha"."""
    datos = datos or {}
    hoy = _dt.date.today()
    anio = None
    a_txt = str(datos.get("periodo_anio") or "").strip()
    if a_txt.isdigit():
        anio = int(a_txt)
    mes = None
    m_txt = str(datos.get("periodo_mes") or "").strip().lower()
    if m_txt.isdigit():
        v = int(m_txt)
        if 1 <= v <= 12:
            mes = v
    elif m_txt in _MESES_ES:
        mes = _MESES_ES[m_txt]
    if anio is None or mes is None:
        try:
            d = _dt.datetime.strptime(str(datos.get("fecha")).strip(), "%d/%m/%Y")
            anio = anio or d.year
            mes = mes or d.month
        except Exception:
            pass
    return anio or hoy.year, mes or hoy.month


def _fecha_o_none(valor):
    """Normaliza un valor de fecha de BD (date/datetime/str ISO o DD/MM/AAAA) a `datetime.date`."""
    if valor is None:
        return None
    if isinstance(valor, _dt.datetime):
        return valor.date()
    if isinstance(valor, _dt.date):
        return valor
    s = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return _dt.datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
        except Exception:
            continue
    return None


def construir_input(datos: dict) -> NominaInput:
    """`self._datos` → NominaInput. Aquí se resuelve la interpretación del salario.

    Fase F.1/F.3 (modelo dual): con `modelo_pago == 'hora'` el bruto NUNCA sale de un salario
    fijo — se calcula a partir de `horas_trabajadas_periodo` (horas REALMENTE fichadas en el
    periodo, ya resueltas por el llamador — GUI o job automático, ambos con acceso a BD) ×
    `tarifa_hora` del contrato. Con `modelo_pago == 'fijo'` (o ausente, compatibilidad) se
    mantiene el comportamiento existente: `salario_base_mensual = datos['salario']` SIN dividir
    (la división anual→mensual, si procede, ya la hace el llamador antes de construir `datos`)."""
    datos = datos or {}
    try:
        num_pagas = int(num(datos.get("num_pagas")) or 12)
    except Exception:
        num_pagas = 12
    modelo_pago = str(datos.get("modelo_pago") or "fijo").strip().lower()
    if modelo_pago == "hora":
        salario_mensual = round(num(datos.get("horas_trabajadas_periodo"))
                                * num(datos.get("tarifa_hora")), 2)
    else:
        salario_mensual = num(datos.get("salario"))          # etiqueta: mensual (sin dividir)
    return NominaInput(
        salario_base_mensual=salario_mensual,
        num_pagas=num_pagas or 12,
        grupo_cotizacion=str(datos.get("grupo_cotizacion") or "7"),
        tipo_contrato=(datos.get("tipo_contrato_ss") or "indefinido"),
        irpf_tipo=_num_o_none(datos.get("irpf_pct")),
        plus_convenio=num(datos.get("plus_convenio")),
        nocturnidad=num(datos.get("nocturnidad")),
        bonus=num(datos.get("bonus")),
        horas_extra=num(datos.get("horas_extras")),
        plus_transporte=num(datos.get("plus_transporte")),
        dietas=num(datos.get("dietas")),
        anticipos=num(datos.get("anticipos")),
        embargos=num(datos.get("embargos")),
    )


def _enriquecer_fase_f(entrada: NominaInput, datos: dict, id_empleado, id_empresa,
                       anio: int, mes: int) -> NominaInput:
    """Añade a `entrada` (ya construida) los datos de Incapacidad Temporal (F4.6.4) y de horas
    extra de bolsa de horas (F4.6.5) del periodo — impuro (consulta BD), reutilizando SIEMPRE
    servicios ya existentes (nunca recalcula lo que ya calculan `ausencias_servicio`/`bolsa_horas`/
    `maestros`). Best-effort: cualquier fallo se registra y se continúa sin la parte afectada (una
    nómina nunca debe dejar de generarse porque un enriquecimiento opcional falle)."""
    # ── 0) IRPF real (Fase F.2) ──────────────────────────────────────────────────────────────
    # Red de seguridad CENTRAL: si el llamador no ha resuelto ya el `irpf_pct` (la GUI lo hace en
    # `_autollenar`, el job automático en `_datos_borrador`), se resuelve aquí — así NINGÚN
    # camino puede acabar aplicando el 15% por defecto del motor a un empleado que sí tiene un
    # IRPF real calculado (Fase B2, `rrhh_datos_fiscales.irpf_pct_calculado`, el ÚNICO campo del
    # que debe leerse, nunca un valor del contrato).
    if entrada.irpf_tipo is None:
        try:
            from src.rrhh.db import datos_fiscales as _df
            df_fiscal = _df.obtener_datos_fiscales(id_empleado, id_empresa)
            if df_fiscal and df_fiscal.get("irpf_pct_calculado") is not None:
                entrada.irpf_tipo = float(df_fiscal.get("irpf_pct_calculado"))
        except Exception as e:
            logger.debug("IRPF real (rrhh_datos_fiscales) de %s no disponible: %s", id_empleado, e)

    # ── 1) Incapacidad Temporal ──────────────────────────────────────────────────────────────
    try:
        from src.rrhh.ausencias_servicio import TIPO_BAJA_MEDICA, listar as _listar_ausencias
        primer = _dt.date(anio, mes, 1)
        ultimo = _dt.date(anio, mes, _calendar.monthrange(anio, mes)[1])
        candidatas = _listar_ausencias(id_empleado, id_empresa=id_empresa, tipo=TIPO_BAJA_MEDICA) or []
        bajas_periodo = []
        for a in candidatas:
            fi, ff = _fecha_o_none(a.get("fecha_inicio")), _fecha_o_none(a.get("fecha_fin"))
            if fi and ff and ff >= primer and fi <= ultimo and a.get("tipo_contingencia"):
                bajas_periodo.append(a)
    except Exception as e:
        logger.debug("_enriquecer_fase_f: listar ausencias de %s: %s", id_empleado, e)
        bajas_periodo = []

    if bajas_periodo:
        # bccc/bccp del MES ANTERIOR APROBADO (rrhh_nominas.conceptos, ya calculados — se
        # reutilizan tal cual, nunca se recalculan desde cero).
        mes_ant, anio_ant = (mes - 1, anio) if mes > 1 else (12, anio - 1)
        bccc_ant = bccp_ant = 0.0
        try:
            from src.rrhh.db import nominas as _db_nominas
            for n in _db_nominas.listar_nominas(id_empleado, id_empresa, anio=anio_ant) or []:
                if n.get("mes") == mes_ant and n.get("estado") == "aprobada":
                    conceptos = json.loads(n.get("conceptos") or "{}")
                    bccc_ant = float(conceptos.get("bccc") or 0.0)
                    bccp_ant = float(conceptos.get("bccp") or 0.0)
                    break
        except Exception as e:
            logger.warning("IT: no se pudo leer la nómina aprobada de %s/%s de %s: %s",
                           mes_ant, anio_ant, id_empleado, e)

        conf = None
        try:
            from src.rrhh import maestros
            contrato = maestros.entidad_contrato(id_empleado, id_empresa) or {}
            conf = {k: contrato.get(k) for k in (
                "complemento_it_activo", "complemento_it_tipo", "complemento_it_porcentaje",
                "complemento_it_tramo_dias_inicio", "complemento_it_tramo_dias_fin")}
        except Exception as e:
            logger.debug("IT: complemento de convenio de %s no disponible: %s", id_empleado, e)

        bajas_it = [{
            "tipo_contingencia": a.get("tipo_contingencia"),
            "fecha_inicio_baja": _fecha_o_none(a.get("fecha_inicio")),
            "fecha_fin_baja": _fecha_o_none(a.get("fecha_fin")),
            "base_cotizacion_mes_anterior": bccc_ant,
            "base_cotizacion_cp_mes_anterior": bccp_ant,
            "configuracion_complemento_convenio": conf,
        } for a in bajas_periodo]
        entrada.bajas_it = bajas_it
        entrada.anio_periodo = anio
        entrada.mes_periodo = mes

    # ── 2) Horas extra de bolsa de horas (F4.6.5, condicional a bolsa_horas_compensacion='pago')
    # Simplificación DOCUMENTADA: `calcular_bolsa_horas_empleado` devuelve el saldo ACUMULADO de
    # toda la vigencia de la bolsa (el motor de la Fase E no lleva un desglose mes a mes de lo ya
    # incorporado a nómina) — se usa tal cual como devengo informativo del mes; no hay en el
    # esquema actual (`rrhh_bolsa_horas`) un campo de "horas ya pagadas" que permita aislar solo
    # el delta del último mes cerrado sin inventar un motor de estado nuevo (fuera de alcance).
    try:
        from src.rrhh import maestros
        contrato = maestros.entidad_contrato(id_empleado, id_empresa) or {}
        if str(contrato.get("bolsa_horas_compensacion") or "") == "pago":
            from src.rrhh.bolsa_horas import calcular_bolsa_horas_empleado, obtener_bolsa_horas
            res_bolsa = calcular_bolsa_horas_empleado(id_empleado, id_empresa=id_empresa)
            horas_empresa = float(res_bolsa.get("horas_compensar_empresa") or 0.0)
            if horas_empresa:
                tarifa = num(contrato.get("tarifa_hora"))
                if not tarifa:
                    bolsa = obtener_bolsa_horas(id_empleado, id_empresa=id_empresa) or {}
                    horas_diarias = num(bolsa.get("horas_diarias"))
                    if horas_diarias:
                        # 21,75 = media de días laborables/mes en España (constante estándar de
                        # nómina) — aproximación documentada a falta de una tarifa/hora explícita
                        # en contratos de salario fijo.
                        tarifa = round(entrada.salario_base_mensual / (horas_diarias * 21.75), 4)
                importe = round(horas_empresa * tarifa, 2)
                if importe:
                    entrada.horas_extra_bolsa_importe = importe
    except ValueError as e:
        logger.debug("bolsa de horas de %s sin datos suficientes: %s", id_empleado, e)
    except Exception as e:
        logger.debug("bolsa de horas de %s: no se pudo calcular el extra: %s", id_empleado, e)

    return entrada


def validar_prerrequisitos_nomina(datos: dict, id_empleado, id_empresa=None) -> None:
    """Valida ANTES de calcular que existan los datos imprescindibles para una nómina real de un
    empleado concreto (contrato, salario/tarifa, IRPF) — Fase G (UX): en vez de dejar que un dato
    ausente propague una excepción críptica más abajo, lanza `GestionNominaError` con un mensaje
    claro de QUÉ falta y DÓNDE completarlo. No-op si `id_empleado` es falsy (compatibilidad total
    con llamadas manuales/tests que calculan sobre datos sueltos sin un empleado real, tal y como
    ya hace `_enriquecer_fase_f`)."""
    if not id_empleado:
        return
    datos = datos or {}
    from src.rrhh import maestros
    contrato = maestros.entidad_contrato(id_empleado, id_empresa) or {}
    if not contrato:
        raise GestionNominaError(
            "No se encontró ningún contrato para este empleado. Date de alta su contrato en la "
            "pestaña 'Contratos' antes de generar la nómina.")

    modelo_pago = str(datos.get("modelo_pago") or contrato.get("modelo_pago") or "fijo").strip().lower()
    if modelo_pago == "hora":
        tarifa_datos = datos.get("tarifa_hora")
        tarifa = num(tarifa_datos) if tarifa_datos not in (None, "") else num(contrato.get("tarifa_hora"))
        if not tarifa:
            raise GestionNominaError(
                "Falta la tarifa por hora del contrato de este empleado. Complétala en la "
                "pestaña 'Contratos' (modelo de pago: por horas) antes de generar la nómina.")
    else:
        salario = num(datos.get("salario"))
        if not salario:
            salario_contrato = num(contrato.get("salario"))
            salario_base_emp = 0.0
            try:
                from src.rrhh.db import empleados as _db_empleados
                emp = _db_empleados.obtener_empleado(id_empleado, id_empresa=id_empresa) or {}
                salario_base_emp = num(emp.get("salario_base"))
            except Exception as e:
                logger.debug("validar_prerrequisitos_nomina: salario_base empleado %s: %s",
                            id_empleado, e)
            if not salario_contrato and not salario_base_emp:
                raise GestionNominaError(
                    "Falta el salario base de este empleado. Complétalo en su expediente o en "
                    "su contrato antes de generar la nómina.")

    if _num_o_none(datos.get("irpf_pct")) is None:
        try:
            from src.rrhh.db import datos_fiscales as _df
            df = _df.obtener_datos_fiscales(id_empleado, id_empresa)
        except Exception as e:
            logger.debug("validar_prerrequisitos_nomina: datos fiscales %s: %s", id_empleado, e)
            df = None
        if not df or df.get("irpf_pct_calculado") is None:
            raise GestionNominaError(
                "Falta el porcentaje de IRPF del empleado. Complétalo en la pestaña 'Modelo "
                "Fiscal Empleados' antes de generar la nómina.")


def calcular_desde_datos(datos: dict, pais: str = "ES", id_empleado=None, id_empresa=None):
    """Punto único: datos → parámetros del año → NominaResultado (del motor puro).

    Fase F: si se conoce `id_empleado` (parámetro explícito o `datos['id_empleado']`), enriquece
    el `NominaInput` con Incapacidad Temporal y horas extra de bolsa de horas del periodo
    (`_enriquecer_fase_f`) — reutilizando servicios ya existentes, nunca recalculando nada por su
    cuenta. Sin `id_empleado` se comporta EXACTAMENTE igual que antes de la Fase F.

    Fase G (UX): con `id_empleado` conocido, valida antes de calcular (`validar_prerrequisitos_
    nomina`) — contrato/salario/tarifa/IRPF — y lanza `GestionNominaError` con un mensaje claro si
    falta algo, en vez de dejar que la ausencia propague un error críptico más abajo."""
    datos = datos or {}
    entrada = construir_input(datos)
    anio, mes = _resolver_periodo(datos)
    id_empleado = id_empleado or datos.get("id_empleado")
    id_empresa = id_empresa or datos.get("id_empresa")
    if id_empleado:
        validar_prerrequisitos_nomina(datos, id_empleado, id_empresa)
        try:
            entrada = _enriquecer_fase_f(entrada, datos, id_empleado, id_empresa, anio, mes)
        except Exception as e:
            logger.error("calcular_desde_datos: enriquecimiento Fase F de %s falló: %s",
                        id_empleado, e)
    parametros = cargar_parametros(anio, pais)
    return calcular_nomina(entrada, parametros)


# ── Fase F.6/F.7 · Generación automática de borradores de fin de mes ────────────────────────
def _datos_borrador(emp: dict, contrato: dict, anio: int, mes: int, id_empresa) -> dict:
    """`datos` mínimo (formato "motor", NO el formato granular del formulario inline — no hace
    falta pasar por `_preparar_engine` porque aquí no hay conceptos sueltos que agregar) para un
    empleado/periodo concretos, listo para `persistencia.registrar_generacion('NÓMINA', ...)`."""
    modelo_pago = str(contrato.get("modelo_pago") or "fijo").strip().lower()
    fecha_periodo = _dt.date(anio, mes, _calendar.monthrange(anio, mes)[1])
    datos = {
        "nif": emp.get("nif"),
        "id_empleado": emp.get("id"),
        "id_empresa": id_empresa,
        "fecha": fecha_periodo.strftime("%d/%m/%Y"),
        "periodo_anio": str(anio),
        "periodo_mes": str(mes),
        "num_pagas": "12",
        "grupo_cotizacion": "7",
        "tipo_contrato_ss": "indefinido",
        "modelo_pago": modelo_pago,
    }
    # IRPF real (Fase B2) — NUNCA un tipo fijo.
    try:
        from src.rrhh.db import datos_fiscales as _df
        df = _df.obtener_datos_fiscales(emp.get("id"), id_empresa)
        if df and df.get("irpf_pct_calculado") is not None:
            datos["irpf_pct"] = str(df.get("irpf_pct_calculado"))
    except Exception as e:
        logger.debug("borrador automático: irpf de %s: %s", emp.get("id"), e)

    if modelo_pago == "hora":
        datos["tarifa_hora"] = str(contrato.get("tarifa_hora") or 0)
        horas = 0.0
        id_usuario = emp.get("id_usuario")
        if id_usuario:
            try:
                from src.db.usuario import listar_fichajes_empleado
                fichajes = listar_fichajes_empleado(id_usuario, anio=anio, mes=mes) or []
                horas = round(sum(int(f.get("segundos") or 0) for f in fichajes) / 3600.0, 2)
            except Exception as e:
                logger.debug("borrador automático: fichajes de %s: %s", emp.get("id"), e)
        datos["horas_trabajadas_periodo"] = str(horas)
    else:
        salario_anual = num(contrato.get("salario")) or (num(emp.get("salario_base")) * 12)
        datos["salario"] = str(round(salario_anual / 12, 2)) if salario_anual else "0"
    return datos


def generar_borradores_mes_cerrado(id_empresa=None) -> str:
    """Job de fin de mes (Fase F.6): genera un borrador de `rrhh_nominas` (`estado='borrador'`,
    el valor por defecto de la columna) para cada empleado ACTIVO con contrato VIGENTE, del MES
    NATURAL CERRADO (el anterior a hoy) — con el motor real (fijo u hora según el contrato,
    IRPF real, IT y bolsa de horas si procede, exactamente igual que la generación manual).

    Escribe SIEMPRE a través del camino de persistencia ya existente y reconectado en F4.3.7
    (`persistencia.registrar_generacion` → `_registrar_nomina`) — el MISMO que usa la pestaña
    Nóminas, nunca duplica su lógica de mapeo de columnas. NUNCA aprueba nada: un humano cambia
    `estado` a 'aprobada' desde el listado de nóminas del expediente del empleado.

    Idempotente: si ya existe CUALQUIER nómina (borrador o aprobada) para ese empleado/año/mes,
    no la duplica — así que reintentos del propio scheduler, o ejecuciones manuales repetidas,
    son seguros."""
    from src.db.empresa import empresa_actual_id
    from src.rrhh import persistencia
    from src.rrhh.db import contratos as _db_contratos
    from src.rrhh.db import empleados as _db_empleados
    from src.rrhh.db import nominas as _db_nominas

    id_empresa = id_empresa or empresa_actual_id()
    hoy = _dt.date.today()
    anio, mes = (hoy.year, hoy.month - 1) if hoy.month > 1 else (hoy.year - 1, 12)

    generados = saltados = fallidos = 0
    for emp in _db_empleados.listar_empleados(id_empresa, estado="activo") or []:
        eid = emp.get("id")
        try:
            ya_existe = any(n.get("mes") == mes
                            for n in (_db_nominas.listar_nominas(eid, id_empresa, anio=anio) or []))
            if ya_existe:
                saltados += 1
                continue
            contratos_emp = _db_contratos.listar_contratos(eid, id_empresa) or []
            contrato = next((c for c in contratos_emp if c.get("estado") == "vigente"), None)
            if not contrato:
                saltados += 1
                continue
            datos = _datos_borrador(emp, contrato, anio, mes, id_empresa)
            eid_reg = persistencia.registrar_generacion("NÓMINA", datos, None, id_empresa=id_empresa)
            if eid_reg:
                generados += 1
            else:
                fallidos += 1
        except Exception as e:
            logger.error("generar_borradores_mes_cerrado(emp=%s): %s", eid, e)
            fallidos += 1
    return (f"borradores generados={generados} saltados={saltados} fallidos={fallidos} "
            f"periodo={mes:02d}/{anio}")


def registrar_jobs_nominas(id_empresa=None):
    """Registra el job programado de generación automática de borradores de nómina de fin de mes
    (mismo patrón `scheduler.registrar`/`registrar_job` ya usado para otras automatizaciones,
    p.ej. `contratos_pro.registrar_jobs_contratos`/`b2b_escrow.registrar_jobs_escrow` — aquí se
    registra el callable con su firma REAL `fn(id_empresa)`, que es como `scheduler.ejecutar_job`
    invoca todo job, en vez de un lambda de 0 argumentos). Degradable: si el Scheduler no está
    disponible, la generación manual desde la pestaña Nóminas sigue funcionando igual."""
    try:
        from src.services import scheduler
        scheduler.registrar("rrhh_nominas_borrador_mensual", generar_borradores_mes_cerrado)
        scheduler.registrar_job("rrhh_nominas_borrador_mensual", intervalo_horas=24,
                                descripcion="RRHH: generación automática de borradores de nómina "
                                           "del mes cerrado (fijo/hora, IRPF real, IT, bolsa de horas)",
                                id_empresa=id_empresa)
    except Exception as e:
        logger.debug("registrar_jobs_nominas: %s", e)
