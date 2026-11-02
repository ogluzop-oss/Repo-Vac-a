"""
Modelo 130 (Pago fraccionado IRPF, estimación directa — autónomos) — FASE B.

Sigue el MISMO patrón de clase/casillas/persistencia que `modelo_303.py`/`modelo_111.py`:
constructor `(ejercicio, periodo, id_empresa)`, `calcular()` interno, `casillas()`,
`generar()` que persiste vía `aeat.base.guardar_declaracion` y produce el PDF con el
generador común `aeat.documento`.

Diferencia clave frente al 303 (que liquida SOLO el trimestre en curso): el 130 es
ACUMULATIVO dentro del ejercicio — las casillas 01/02 (ingresos/gastos) suman desde el
1 de enero del ejercicio hasta el FIN del trimestre declarado, no solo el trimestre
aislado (art. 23/24 RD 439/2007). Reutiliza `contabilidad.informes.perdidas_ganancias`
(parametrizada con el rango acumulado) para ese resultado de actividad — no se duplica
la agregación contable.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.aeat import base as _B
from src.services.aeat import estados as _E
from src.services.aeat.modelo_303 import _rango as _rango_periodo

logger = logging.getLogger("aeat.m130")

MODELO = "130"
PERIODOS = ("1T", "2T", "3T", "4T")
TIPO_PAGO_FRACCIONADO = 20.0   # % s/rendimiento neto acumulado (art. 110.3 RIRPF)


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.fiscal.identidad_fiscal import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        if id_empresa:
            return id_empresa
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return EMPRESA_DEFAULT_ID


def periodos_validos() -> tuple:
    """El 130 SOLO se declara por trimestre (nunca mensual ni anual, a diferencia del 303)."""
    return PERIODOS


def _orden(periodo) -> int:
    return PERIODOS.index(periodo)


def _rango_acumulado(ejercicio, periodo):
    """(desde, hasta) ACUMULADO: 1 de enero del ejercicio → fin del trimestre declarado."""
    try:
        from src.services.contabilidad import informes as _INF
        return _INF.rango_acumulado_trimestre(ejercicio, periodo)
    except Exception:
        _, hasta = _rango_periodo(ejercicio, periodo)
        return f"{int(ejercicio)}-01-01", hasta


def _resultado_actividad_acumulado(id_empresa, ejercicio, periodo) -> dict:
    """Ingresos/gastos ACUMULADOS desde el 1 de enero hasta fin del trimestre, vía
    `informes.perdidas_ganancias` (parametrizada) — no se recalcula el mayor contable
    desde cero."""
    from src.services.contabilidad import informes as _INF
    try:
        return _INF.perdidas_ganancias_periodo(ejercicio, periodo, id_empresa=id_empresa,
                                               acumulado=True)
    except AttributeError:
        # Fallback defensivo si informes.py no expusiera aún el wrapper (no debería ocurrir).
        desde, hasta = _rango_acumulado(ejercicio, periodo)
        return _INF.perdidas_ganancias(id_empresa, desde=desde, hasta=hasta)


def _retenciones_soportadas(id_empresa, desde, hasta) -> float:
    """Retenciones IRPF que TERCEROS han practicado sobre facturas emitidas por el propio
    autónomo (`facturas_cliente.retencion_importe`, facturas a otras empresas/profesionales
    que retienen en origen) EN EL TRIMESTRE (no acumulado: art. 110.3.c RIRPF solo permite
    deducir en cada trimestre las retenciones soportadas EN ESE trimestre)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(retencion_importe),0) FROM facturas_cliente "
                "WHERE id_empresa=%s AND estado NOT IN ('anulada','borrador') "
                "AND fecha_emision BETWEEN %s AND %s", (id_empresa, desde, hasta))
            r = cur.fetchone()
            v = (list(r.values())[0] if isinstance(r, dict) else r[0]) if r else 0
            return round(float(v or 0), 2)
    except Exception as e:
        logger.error("_retenciones_soportadas: %s", e)
        return 0.0


def _pagos_fraccionados_previos(id_empresa, ejercicio, periodo) -> float:
    """Suma de los resultados YA declarados (no ANULADOS) de este mismo modelo/ejercicio
    en trimestres ANTERIORES al indicado — casilla 05 (deducción). `resultado` en
    `aeat_declaraciones` es siempre el importe final ya con el suelo de 0 aplicado, que es
    exactamente lo que la normativa exige deducir (lo efectivamente liquidado, no un
    teórico)."""
    orden_actual = _orden(periodo)
    total = 0.0
    try:
        for d in _B.listar_declaraciones(modelo=MODELO, ejercicio=ejercicio, id_empresa=id_empresa):
            p = d.get("periodo")
            if p in PERIODOS and _orden(p) < orden_actual and d.get("estado") != _E.ANULADO:
                total += float(d.get("resultado") or 0)
    except Exception as e:
        logger.error("_pagos_fraccionados_previos: %s", e)
    return round(total, 2)


class Modelo130:
    """Pago fraccionado IRPF por casillas. `casillas()` → [{casilla, descripcion, importe}]."""

    def __init__(self, ejercicio, periodo, id_empresa=None, deducciones_aceptadas=None):
        if periodo not in PERIODOS:
            raise ValueError(f"periodo inválido para 130 (solo trimestres): {periodo}")
        self.ejercicio = int(ejercicio)
        self.periodo = periodo
        self.id_empresa = _emp(id_empresa)
        self.desde_trim, self.hasta_trim = _rango_periodo(ejercicio, periodo)
        self.desde, self.hasta = _rango_acumulado(ejercicio, periodo)
        # Deducciones sectoriales ACEPTADAS por el usuario en el Paso 3 de la Calculadora Fiscal
        # (`gui/calculadora_fiscal_wizard.py`), shape `{'concepto','tipo','importe'}` — `importe` ya
        # en euros (calculado allí a partir de porcentaje/importe_fijo + la base/cantidad real que
        # facilitó el usuario, nunca inventado aquí). Opcional: por defecto (None/[]) el resultado es
        # IDÉNTICO al cálculo de antes de esta integración.
        self.deducciones_aceptadas = list(deducciones_aceptadas or [])
        self._calcular()

    def _calcular(self):
        from src.services.contabilidad.fiscal_deducciones import separar_por_tipo
        pyg = _resultado_actividad_acumulado(self.id_empresa, self.ejercicio, self.periodo)
        ingresos = round(float(pyg.get("ingresos") or 0), 2)
        gastos_contables = round(float(pyg.get("gastos") or 0), 2)
        # 'gasto': deducciones sectoriales que son gasto deducible ADICIONAL (suministros del hogar,
        # dietas, vehículo — art. 9/11 RIRPF) → se suman a la bolsa de gastos ANTES del rendimiento
        # neto, exactamente como cualquier otro gasto deducible ya contabilizado (misma casilla 02,
        # sin casilla nueva: es legalmente lo mismo, solo que reconocido fuera de la contabilidad
        # formal). 'cuota': créditos fiscales que restarían del resultado final (07) — hoy sin ningún
        # concepto sembrado de este tipo, ver `fiscal_deducciones.CONCEPTOS_CUOTA`.
        ded_gasto, ded_cuota = separar_por_tipo(self.deducciones_aceptadas)
        gastos = round(gastos_contables + ded_gasto, 2)
        rendimiento_neto = round(ingresos - gastos, 2)
        # Tipo del 20% solo se aplica sobre rendimiento neto POSITIVO (en pérdidas
        # acumuladas no hay pago fraccionado que calcular, no un importe negativo).
        pago_fraccionado = round(max(0.0, rendimiento_neto) * TIPO_PAGO_FRACCIONADO / 100.0, 2)
        deduccion_previos = _pagos_fraccionados_previos(self.id_empresa, self.ejercicio, self.periodo)
        retenciones = _retenciones_soportadas(self.id_empresa, self.desde_trim, self.hasta_trim)

        cas = []

        def add(c, desc, imp):
            cas.append({"casilla": c, "descripcion": desc, "importe": round(float(imp), 2)})

        desc_02 = "Gastos deducibles del ejercicio (acumulado desde el 1 de enero)"
        if ded_gasto:
            desc_02 += f" (incluye {ded_gasto:,.2f} € de deducciones sectoriales aceptadas)"
        add("01", "Ingresos íntegros del ejercicio (acumulado desde el 1 de enero)", ingresos)
        add("02", desc_02, gastos)
        add("03", "Rendimiento neto (01-02)", rendimiento_neto)
        add("04", f"Pago fraccionado ({TIPO_PAGO_FRACCIONADO:.0f}% s/03, mínimo 0)", pago_fraccionado)
        add("05", "Deducción: pagos fraccionados de trimestres anteriores (mismo ejercicio)",
            deduccion_previos)
        add("06", "Retenciones e ingresos a cuenta soportados en el periodo", retenciones)
        desc_07 = "Resultado de la liquidación (04-05-06; nunca negativo)"
        if ded_cuota:
            desc_07 = "Resultado de la liquidación (04-05-06, menos deducciones sectoriales de " \
                     "cuota aceptadas; nunca negativo)"
        resultado_bruto = round(pago_fraccionado - deduccion_previos - retenciones - ded_cuota, 2)
        resultado = max(0.0, resultado_bruto)   # nunca negativo: si sale <0, el resultado es 0
        add("07", desc_07, resultado)

        self._casillas = cas
        self.resultado = resultado
        self.sentido = "a ingresar" if resultado > 0 else "sin cuota a ingresar"
        self.deducciones_sectoriales_gasto = ded_gasto
        self.deducciones_sectoriales_cuota = ded_cuota

    def casillas(self) -> list:
        return list(self._casillas)

    def como_dict(self) -> dict:
        return {"modelo": MODELO, "ejercicio": self.ejercicio, "periodo": self.periodo,
                "desde": self.desde, "hasta": self.hasta, "resultado": self.resultado,
                "sentido": self.sentido, "casillas": self.casillas(),
                "deducciones_sectoriales_gasto": self.deducciones_sectoriales_gasto,
                "deducciones_sectoriales_cuota": self.deducciones_sectoriales_cuota}


def generar_pdf(modelo130: "Modelo130", id_declaracion, hash_doc, id_empresa=None) -> str | None:
    """Documento borrador PDF del 130 (delegado en el helper común aeat.documento, el
    MISMO generador que usan 303/111 — no se crea uno nuevo)."""
    from src.services.aeat import documento as _D
    return _D.generar_pdf(modelo="130", titulo="Modelo 130 — Pago fraccionado IRPF (borrador)",
                          ejercicio=modelo130.ejercicio, periodo=modelo130.periodo,
                          id_declaracion=id_declaracion, casillas=modelo130.casillas(),
                          resultado=modelo130.resultado, sentido=modelo130.sentido,
                          hash_doc=hash_doc, id_empresa=_emp(id_empresa))


def generar(ejercicio, periodo, *, id_empresa=None, usuario=None, observaciones=None,
           deducciones_aceptadas=None) -> dict:
    """Genera (idempotente) el Modelo 130 del trimestre: calcula casillas (acumulado YTD),
    persiste la declaración (estado GENERADO), produce el PDF borrador y lo enlaza. Devuelve
    {ok, id, resultado, sentido, casillas, pdf}. Si ya existe PRESENTADA para la clave, no la
    sobreescribe (idéntico contrato que 303/111). `deducciones_aceptadas`: opcional, ver
    `Modelo130.__init__` — omitido/None produce el mismo resultado que antes de esta integración."""
    id_empresa = _emp(id_empresa)
    m = Modelo130(ejercicio, periodo, id_empresa, deducciones_aceptadas=deducciones_aceptadas)
    did = _B.guardar_declaracion(MODELO, ejercicio, periodo, m.resultado, m.casillas(),
                                 observaciones=observaciones, usuario=usuario, id_empresa=id_empresa)
    if not did:
        return {"ok": False, "errores": "declaración ya presentada (no se sobreescribe)"}
    decl = _B.obtener_declaracion(did, id_empresa=id_empresa)
    pdf = generar_pdf(m, did, decl.get("hash"), id_empresa=id_empresa)
    if pdf:
        _B.guardar_fichero(did, pdf, id_empresa=id_empresa)
    return {"ok": True, "id": did, "resultado": m.resultado, "sentido": m.sentido,
            "casillas": m.casillas(), "pdf": pdf, "hash": decl.get("hash")}
