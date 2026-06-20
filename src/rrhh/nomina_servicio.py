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

import datetime as _dt
import logging

from src.rrhh.nomina_motor import NominaInput, calcular_nomina
from src.rrhh.parametros_cotizacion import cargar_parametros

logger = logging.getLogger("rrhh.nomina_servicio")


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


def construir_input(datos: dict) -> NominaInput:
    """`self._datos` → NominaInput. Aquí se resuelve la interpretación del salario."""
    datos = datos or {}
    try:
        num_pagas = int(num(datos.get("num_pagas")) or 12)
    except Exception:
        num_pagas = 12
    return NominaInput(
        salario_base_mensual=num(datos.get("salario")),     # etiqueta: mensual (sin dividir)
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


def calcular_desde_datos(datos: dict, pais: str = "ES"):
    """Punto único: datos → parámetros del año → NominaResultado (del motor puro)."""
    entrada = construir_input(datos)
    parametros = cargar_parametros(_anio(datos or {}), pais)
    return calcular_nomina(entrada, parametros)
