"""
Gestión operativa de AUSENCIAS (F4.7).

Lógica de negocio sobre `rrhh_ausencias` (capa db existente): alta/edición/consulta
con tipos normalizados y validaciones (fechas, días, solapamientos incompatibles). No
crea tablas. Multiempresa. Sin Qt. Reutiliza el calendario común con vacaciones.
"""

import datetime as _dt
import logging

from src.rrhh.db import ausencias as _db
from src.rrhh.vacaciones_servicio import GestionLaboralError, _dias_naturales, _fecha, _solapa

logger = logging.getLogger("rrhh.ausencias")

# Tipos mínimos soportados (clave técnica ≤14 chars por rrhh_ausencias.tipo VARCHAR(14)
# → etiqueta legible).
TIPOS = {
    "enfermedad": "Enfermedad / baja médica",
    "permiso_ret": "Permiso retribuido",
    "permiso_noret": "Permiso no retribuido",
    "accidente": "Accidente",
    "maternidad": "Maternidad",
    "paternidad": "Paternidad",
    "otros": "Otros",
}

# Único tipo de esta tabla que representa una baja médica (Fase A/C del sistema de bolsa de
# horas + IT): es el que habilita el desplegable de `tipo_contingencia` en el formulario y el
# único para el que ese dato tiene sentido — el motor de Incapacidad Temporal (Fase F) lo usa
# para elegir la tabla de tramos/porcentajes correcta.
TIPO_BAJA_MEDICA = "enfermedad"

# Contingencias de una baja médica (`rrhh_ausencias.tipo_contingencia`, migración 0264). Clave
# técnica = valor persistido en BD (VARCHAR libre, no ENUM); valor = etiqueta legible.
TIPOS_CONTINGENCIA = {
    "CONTINGENCIAS_COMUNES": "Contingencias comunes",
    "CONTINGENCIAS_PROFESIONALES": "Contingencias profesionales",
    "MENSTRUACION_INCAPACITANTE": "Menstruación incapacitante",
    "INTERRUPCION_EMBARAZO_GESTACION": "Interrupción del embarazo (gestación)",
    "NACIMIENTO_CUIDADO_MENOR": "Nacimiento y cuidado del menor",
}


def _existe_solapamiento(id_empleado, id_empresa, fi, ff, excluir_id=None) -> bool:
    for f in _db.listar_ausencias(id_empleado, id_empresa):
        if excluir_id and f.get("id") == excluir_id:
            continue
        if not f.get("fecha_inicio") or not f.get("fecha_fin"):
            continue
        if _solapa(fi, ff, _fecha(f["fecha_inicio"]), _fecha(f["fecha_fin"])):
            return True
    return False


def registrar(id_empleado, tipo, fecha_inicio, fecha_fin, motivo="", justificada=False,
              tipo_contingencia=None, id_empresa=None) -> int:
    """Alta de ausencia. Valida tipo, fechas, días y solapamiento incompatible.

    `tipo_contingencia` (Fase A/C): solo tiene sentido cuando `tipo == TIPO_BAJA_MEDICA`
    ("enfermedad") — se fuerza a None en cualquier otro tipo para no dejar basura en un campo
    que luego interpreta el motor de IT (Fase F)."""
    if tipo not in TIPOS:
        raise GestionLaboralError(f"Tipo de ausencia no válido: {tipo!r}.")
    if tipo_contingencia and tipo_contingencia not in TIPOS_CONTINGENCIA:
        raise GestionLaboralError(f"Tipo de contingencia no válido: {tipo_contingencia!r}.")
    if tipo != TIPO_BAJA_MEDICA:
        tipo_contingencia = None
    fi, ff = _fecha(fecha_inicio), _fecha(fecha_fin)
    dias = _dias_naturales(fi, ff)
    if _existe_solapamiento(id_empleado, id_empresa, fi, ff):
        raise GestionLaboralError("Las fechas se solapan con otra ausencia registrada.")
    aid = _db.crear_ausencia(id_empleado, id_empresa, tipo=tipo, fecha_inicio=fi.isoformat(),
                             fecha_fin=ff.isoformat(), dias=dias, motivo=motivo,
                             justificada=1 if justificada else 0,
                             tipo_contingencia=tipo_contingencia)
    if not aid:
        raise GestionLaboralError("No se pudo registrar la ausencia.")
    return aid


def editar(id_ausencia, id_empresa=None, **campos) -> bool:
    """Edita una ausencia. Si cambian fechas, revalida y comprueba solapamiento."""
    actual = _db.obtener_ausencia(id_ausencia, id_empresa)
    if not actual:
        raise GestionLaboralError("Ausencia no encontrada.")
    if "tipo" in campos and campos["tipo"] not in TIPOS:
        raise GestionLaboralError(f"Tipo de ausencia no válido: {campos['tipo']!r}.")
    fi = _fecha(campos.get("fecha_inicio") or actual["fecha_inicio"])
    ff = _fecha(campos.get("fecha_fin") or actual["fecha_fin"])
    dias = _dias_naturales(fi, ff)
    if ("fecha_inicio" in campos or "fecha_fin" in campos) and \
            _existe_solapamiento(actual["id_empleado"], id_empresa, fi, ff, excluir_id=id_ausencia):
        raise GestionLaboralError("Las nuevas fechas se solapan con otra ausencia.")
    if "fecha_inicio" in campos:
        campos["fecha_inicio"] = fi.isoformat()
    if "fecha_fin" in campos:
        campos["fecha_fin"] = ff.isoformat()
    if "fecha_inicio" in campos or "fecha_fin" in campos:
        campos["dias"] = dias
    if "justificada" in campos:
        campos["justificada"] = 1 if campos["justificada"] else 0
    return _db.actualizar_ausencia(id_ausencia, id_empresa, **campos)


def eliminar(id_ausencia, id_empresa=None) -> bool:
    """Elimina una ausencia registrada."""
    actual = _db.obtener_ausencia(id_ausencia, id_empresa)
    if not actual:
        raise GestionLaboralError("Ausencia no encontrada.")
    return _db.eliminar_ausencia(id_ausencia, id_empresa)


def listar(id_empleado, id_empresa=None, tipo=None) -> list:
    return _db.listar_ausencias(id_empleado, id_empresa, tipo=tipo)


# ── Calendario (vista simple combinada vacaciones + ausencias) ─────────────────
def calendario(id_empleado, id_empresa=None, anio=None) -> list:
    """Eventos del empleado (vacaciones aprobadas + ausencias) ordenados por fecha.
    Vista simple reutilizable por la GUI. Multiempresa por id_empresa."""
    from src.rrhh.vacaciones_servicio import APROBADA, listar as listar_vac
    eventos = []
    for v in listar_vac(id_empleado, id_empresa, anio=anio):
        if v.get("estado") == APROBADA and v.get("fecha_inicio"):
            eventos.append({"tipo": "Vacaciones", "estado": v.get("estado"),
                            "fecha_inicio": v.get("fecha_inicio"), "fecha_fin": v.get("fecha_fin"),
                            "dias": v.get("dias")})
    for a in _db.listar_ausencias(id_empleado, id_empresa):
        if a.get("fecha_inicio"):
            eventos.append({"tipo": TIPOS.get(a.get("tipo"), a.get("tipo")), "estado": "ausencia",
                            "fecha_inicio": a.get("fecha_inicio"), "fecha_fin": a.get("fecha_fin"),
                            "dias": a.get("dias")})
    eventos.sort(key=lambda e: str(e["fecha_inicio"]))
    return eventos
