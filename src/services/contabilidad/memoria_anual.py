"""
Memoria (Cuentas Anuales). Orquestador de SOLO LECTURA que ensambla el contenido textual/
estructurado de la Memoria del PGC-PYMES a partir de motores REALES ya existentes — contabilidad
(`informes.py`, `cuentas.py`), inmovilizado (`services.finanzas.inmovilizado`), financiación
(`services.finanzas.financiacion`), la calculadora fiscal (`calculadora_fiscal.py`) y el nuevo
registro de partes vinculadas (`partes_vinculadas.py`). No crea ningún motor paralelo ni recalcula
nada que ya calcule otro servicio.

Honestidad (regla dura, sin excepciones): donde un dato que exige la Memoria NO está disponible
hoy en el sistema (objeto social, forma jurídica, método de valoración de existencias si no
estuviera configurado...), se etiqueta explícitamente "no disponible"/"no configurado" — nunca se
rellena con un valor inventado o un supuesto por defecto no verificable.

Nota de alcance: las tablas de Balance de Situación / ECPN / Estado de Flujos de Efectivo las
construye un servicio HERMANO (`balance_situacion.py`/`ecpn.py`/`estado_flujos.py`, en curso en
paralelo) — esta Memoria no las recalcula ni depende de que ya existan; cuando estén disponibles,
un orquestador posterior las combinará con esta salida.
"""

import datetime as _dt
import logging

logger = logging.getLogger("contab.memoria_anual")

_CUENTA_CAPITAL_SOCIAL = "100"
_CUENTA_RESERVA_LEGAL = "112"

# Boilerplate legal: lenguaje estándar que cualquier PYME española incluye en su Memoria —
# referencia normativa genérica, no una afirmación fabricada sobre ESTA empresa en concreto.
_DECLARACION_CUMPLIMIENTO = (
    "Las presentes cuentas anuales se han formulado de acuerdo con el Código de Comercio, el "
    "texto refundido de la Ley de Sociedades de Capital (Real Decreto Legislativo 1/2010) y el "
    "Plan General de Contabilidad de Pequeñas y Medianas Empresas (Real Decreto 1515/2007, y sus "
    "modificaciones posteriores), aplicando los principios contables y criterios de valoración "
    "establecidos en dicha normativa, de forma que muestran la imagen fiel del patrimonio, de la "
    "situación financiera y de los resultados de la empresa. No se han aplicado excepciones a "
    "dichos principios contables salvo las que, en su caso, se indiquen expresamente en esta "
    "Memoria."
)


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
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID


# ── 1. Actividad de la empresa ────────────────────────────────────────────────
def _actividad_empresa(id_empresa) -> dict:
    """Datos de identificación de la empresa, reutilizando la ÚNICA fuente de verdad
    (`empresa.datos_corporativos`). `forma_juridica` y `objeto_social` NO existen hoy como campos
    en `empresas` (confirmado: tabla sin esas columnas) — se reportan honestamente como no
    configurados en vez de asumir un valor. Los administradores salen de los representantes
    legales activos (`representantes_legales.cargo`), que SÍ es un dato real ya capturado."""
    avisos = []
    try:
        from src.db.empresa import datos_corporativos
        dc = datos_corporativos(id_empresa=id_empresa)
    except Exception as e:
        logger.error("_actividad_empresa datos_corporativos: %s", e)
        dc = {}
    emp = dc.get("empresa") or {}

    try:
        from src.db.representantes import listar_representantes
        representantes = listar_representantes(id_empresa, solo_activos=True) or []
    except Exception as e:
        logger.debug("_actividad_empresa representantes: %s", e)
        representantes = []
    administradores = [
        {"nombre": " ".join(p for p in (r.get("nombre"), r.get("apellidos")) if p).strip(),
         "cargo": r.get("cargo") or "no especificado", "dni_nie": r.get("dni_nie")}
        for r in representantes
    ]
    if not administradores:
        avisos.append(
            "No hay ningún representante legal/administrador dado de alta en el sistema "
            "(pantalla de datos corporativos) — esta sección debe completarse manualmente.")

    forma_juridica = emp.get("forma_juridica")  # no existe como columna hoy: siempre None
    objeto_social = emp.get("objeto_social")    # ídem
    if not forma_juridica:
        avisos.append(
            "Forma jurídica: no configurada en el sistema (no existe hoy un campo para ello en "
            "los datos corporativos de la empresa) — completar manualmente antes de presentar.")
    if not objeto_social:
        avisos.append(
            "Objeto social: no configurado en el sistema (no existe hoy un campo para ello en "
            "los datos corporativos de la empresa) — completar manualmente antes de presentar.")

    return {
        "razon_social": emp.get("razon_social") or emp.get("nombre_empresa") or "",
        "cif": emp.get("cif_nif") or "",
        "domicilio": emp.get("direccion_fiscal") or "",
        "forma_juridica": forma_juridica or "no disponible",
        "objeto_social": objeto_social or "no disponible",
        "administradores": administradores,
        "avisos": avisos,
    }


# ── 2. Normas de valoración ───────────────────────────────────────────────────
def _normas_valoracion() -> dict:
    """Método de amortización REAL del inmovilizado (siempre lineal: `inmovilizado.cuota_mensual`
    calcula (coste-residual)/vida_útil en meses a cuota constante, sin otro método configurable
    hoy) y método de valoración de existencias REAL (`articulos.coste_medio`, precio medio
    ponderado recalculado en cada recepción — ver `db/compras.py`). Ninguno de los dos se asume:
    son los que de hecho ejecuta el código."""
    return {
        "inmovilizado_material": {
            "metodo": "lineal",
            "detalle": ("Amortización lineal: (valor de adquisición − valor residual) / vida útil "
                       "en meses, cuota constante (services.finanzas.inmovilizado). Es el único "
                       "método que ejecuta el sistema hoy — no hay otros métodos configurables "
                       "(degresivo, números dígitos...)."),
        },
        "existencias": {
            "metodo": "precio_medio_ponderado",
            "detalle": ("Precio medio ponderado (PMP): `articulos.coste_medio` se recalcula en "
                       "cada recepción de compra (services/db de compras) ponderando stock y "
                       "coste anteriores contra la nueva entrada. Es el método que de hecho "
                       "aplica el sistema — no se asume FIFO ni otro criterio no implementado."),
        },
    }


# ── 3. Desglose del inmovilizado ──────────────────────────────────────────────
def _inmovilizado(anio, id_empresa) -> dict:
    from src.services.finanzas.inmovilizado import listar_activos, valor_neto_contable
    activos = listar_activos(id_empresa=id_empresa) or []
    filas = []
    total_adquisicion = total_amortizado = total_neto = 0.0
    for a in activos:
        adquisicion = round(float(a.get("valor_adquisicion") or 0), 2)
        amortizado = round(float(a.get("amortizado_acumulado") or 0), 2)
        neto = valor_neto_contable(a["id"], id_empresa=id_empresa)
        total_adquisicion += adquisicion
        total_amortizado += amortizado
        total_neto += neto
        filas.append({
            "codigo": a.get("codigo"), "descripcion": a.get("descripcion"),
            "categoria": a.get("categoria"), "estado": a.get("estado"),
            "fecha_alta": str(a.get("fecha_alta") or ""),
            "valor_adquisicion": adquisicion, "amortizado_acumulado": amortizado,
            "valor_neto_contable": neto, "vida_util_meses": a.get("vida_util_meses"),
        })
    return {
        "activos": filas,
        "total_valor_adquisicion": round(total_adquisicion, 2),
        "total_amortizado_acumulado": round(total_amortizado, 2),
        "total_valor_neto_contable": round(total_neto, 2),
        "num_activos": len(filas),
    }


# ── 4. Deudas y vencimientos ───────────────────────────────────────────────────
def _deudas_y_vencimientos(anio, id_empresa) -> dict:
    """Desglose de deuda financiera viva a 31/12/`anio` por corto/largo plazo, usando el motor
    REAL de financiación (`services.finanzas.financiacion`) que ya modela el cuadro de
    amortización cuota a cuota (con fecha de vencimiento de cada principal pendiente) — la
    distinción corto/largo (vencimiento dentro/fuera de los 12 meses siguientes al cierre) se
    deriva de esas fechas reales, no se inventa."""
    from src.services.finanzas import financiacion as FIN
    corte_corto_plazo = f"{anio + 1}-12-31"
    corto, largo = 0.0, 0.0
    detalle = []
    try:
        financiaciones = FIN.listar(id_empresa=id_empresa) or []
    except Exception as e:
        logger.error("_deudas_y_vencimientos listar: %s", e)
        financiaciones = []
    for f in financiaciones:
        try:
            cuadro = FIN.cuadro(f["id"])
        except Exception as e:
            logger.debug("_deudas_y_vencimientos cuadro(%s): %s", f.get("id"), e)
            cuadro = []
        pend_corto = pend_largo = 0.0
        for c in cuadro:
            if (c.get("estado") or "").lower() == "pagada":
                continue
            principal = round(float(c.get("principal") or 0), 2)
            if str(c.get("fecha")) <= corte_corto_plazo:
                pend_corto += principal
            else:
                pend_largo += principal
        corto += pend_corto
        largo += pend_largo
        detalle.append({
            "codigo": f.get("codigo"), "tipo": f.get("tipo"), "entidad": f.get("entidad"),
            "saldo_pendiente": round(float(f.get("saldo_pendiente") or 0), 2),
            "corto_plazo": round(pend_corto, 2), "largo_plazo": round(pend_largo, 2),
            "estado": f.get("estado"),
        })
    try:
        deuda_viva = FIN.deuda_viva(id_empresa=id_empresa)
    except Exception as e:
        logger.debug("_deudas_y_vencimientos deuda_viva: %s", e)
        deuda_viva = {"total": 0.0, "por_tipo": {}}
    return {
        "corto_plazo": round(corto, 2), "largo_plazo": round(largo, 2),
        "total": round(corto + largo, 2),
        "por_tipo": deuda_viva.get("por_tipo", {}),
        "detalle_financiaciones": detalle,
        "nota": ("Desglose derivado del cuadro de amortización real de cada financiación "
                "(préstamo/leasing/renting/póliza) dada de alta en el sistema. Deuda contraída "
                "fuera de este motor (p. ej. un préstamo registrado solo con un asiento manual "
                "en Contabilidad, sin alta en Financiación) NO aparece aquí — revisar también el "
                "Balance de Situación (grupos PGC 1/5) para contraste."),
    }


# ── 5. Conciliación fiscal (resultado contable vs base imponible IS) ─────────
def _conciliacion_fiscal(anio, id_empresa) -> dict:
    """Reutiliza el resultado contable real (`informes.perdidas_ganancias`) y la calculadora
    fiscal YA existente (`calculadora_fiscal.simular`) para estimar la base imponible/cuota del
    Impuesto de Sociedades — no se construye un segundo motor de IS. El modelo de la calculadora
    fiscal no distingue diferencias permanentes/temporales (gasto no deducible, etc.): se avisa
    honestamente de esa limitación en vez de inventar un ajuste."""
    from src.services.contabilidad.informes import perdidas_ganancias
    from src.services.contabilidad.calculadora_fiscal import datos_reales_sugeridos, simular

    pyg = perdidas_ganancias(id_empresa=id_empresa, anio=anio) or {}
    resultado_contable = round(float(pyg.get("resultado") or 0), 2)

    sugeridos = datos_reales_sugeridos(id_empresa=id_empresa, anio=anio) or {}
    sim = simular(
        ingresos_brutos=sugeridos.get("ingresos_brutos") or pyg.get("ingresos") or 0.0,
        gastos_operativos=sugeridos.get("gastos_operativos") or pyg.get("gastos") or 0.0,
        id_empresa=id_empresa,
    )
    ajuste_extracontable = round(float(sim.get("base_imponible", 0.0)) - resultado_contable, 2)

    return {
        "resultado_contable": resultado_contable,
        "ajustes_extracontables": ajuste_extracontable,
        "base_imponible_estimada": sim.get("base_imponible"),
        "tipo_general_pct": sim.get("tipo_general_pct"),
        "cuota_integra_estimada": sim.get("cuota_integra"),
        "deducciones_estimadas": sim.get("total_deducciones"),
        "impuesto_final_estimado": sim.get("impuesto_final"),
        "reglas_fiscales_faltantes": sim.get("reglas_faltantes") or [],
        "nota": (
            sim.get("nota_legal", "") + " Esta conciliación asume que no existen diferencias "
            "permanentes/temporales entre el resultado contable y la base imponible distintas de "
            "las deducciones configuradas en el sistema (el motor actual no modela gastos no "
            "deducibles, diferencias de imputación temporal, etc.); si la empresa tiene ajustes "
            "extracontables conocidos, deben añadirse manualmente antes de presentar el Impuesto "
            "de Sociedades."
        ),
    }


# ── 6. Operaciones con partes vinculadas ──────────────────────────────────────
def _partes_vinculadas(anio, id_empresa) -> dict:
    from src.services.contabilidad.partes_vinculadas import listar_partes_vinculadas
    operaciones = listar_partes_vinculadas(anio, id_empresa=id_empresa) or []
    if not operaciones:
        texto = "No se han registrado operaciones con partes vinculadas durante el ejercicio."
    else:
        total = round(sum(float(o.get("importe") or 0) for o in operaciones), 2)
        texto = (f"Se han registrado {len(operaciones)} operación(es) con partes vinculadas por "
                f"un importe total de {total:,.2f} €.")
    return {"operaciones": operaciones, "texto": texto}


# ── Orquestador público ───────────────────────────────────────────────────────
def generar_memoria(anio, id_empresa=None) -> dict:
    """Memoria del ejercicio `anio`, lista para que el generador de PDF (`cuentas_anuales_pdf.py`)
    y, más adelante, el orquestador de Cuentas Anuales la consuman. Agrega SOLO datos reales ya
    existentes en el sistema; etiqueta honestamente cualquier hueco genuino."""
    anio = int(anio)
    id_empresa = _empresa(id_empresa)

    return {
        "anio": anio,
        "id_empresa": id_empresa,
        "generado": _dt.datetime.now().isoformat(timespec="seconds"),
        "actividad_empresa": _actividad_empresa(id_empresa),
        "declaracion_cumplimiento": _DECLARACION_CUMPLIMIENTO,
        "normas_valoracion": _normas_valoracion(),
        "inmovilizado": _inmovilizado(anio, id_empresa),
        "deudas": _deudas_y_vencimientos(anio, id_empresa),
        "conciliacion_fiscal": _conciliacion_fiscal(anio, id_empresa),
        "partes_vinculadas": _partes_vinculadas(anio, id_empresa),
    }
