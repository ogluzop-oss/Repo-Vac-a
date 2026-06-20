"""
Gestión operativa de VACACIONES (F4.7).

Lógica de negocio sobre `rrhh_vacaciones` (capa db ya existente): saldo, solicitud,
aprobación/denegación/cancelación y validaciones (fechas, días, solapamientos). No crea
tablas; reutiliza columnas existentes (no hay columna de observaciones → se omite, según
permite la estructura). Multiempresa: todo filtrado por id_empresa. Sin Qt.
"""

import datetime as _dt
import logging

from src.rrhh.db import vacaciones as _db

logger = logging.getLogger("rrhh.vacaciones")

DIAS_ANUALES_DEFECTO = 30
PENDIENTE, APROBADA, DENEGADA, CANCELADA, CONSUMIDA = (
    "pendiente", "aprobada", "denegada", "cancelada", "consumida")
_ACTIVOS = (PENDIENTE, APROBADA, CONSUMIDA)   # cuentan para saldo/solapamiento


class GestionLaboralError(Exception):
    """Validación de negocio fallida (fechas, días, solapamiento, estado)."""


def _fecha(v) -> _dt.date:
    if isinstance(v, _dt.date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise GestionLaboralError(f"Fecha no válida: {v!r}")


def _dias_naturales(fi: _dt.date, ff: _dt.date) -> int:
    if ff < fi:
        raise GestionLaboralError("La fecha de fin no puede ser anterior a la de inicio.")
    return (ff - fi).days + 1


def _solapa(a_ini, a_fin, b_ini, b_fin) -> bool:
    return a_ini <= b_fin and b_ini <= a_fin


# ── Saldo ──────────────────────────────────────────────────────────────────────
def saldo(id_empleado, anio=None, id_empresa=None, dias_anuales=DIAS_ANUALES_DEFECTO) -> dict:
    """Saldo de vacaciones del empleado/año. `dias_anuales` configurable (convenio/jornada
    en fases futuras). disponibles = asignados − disfrutados − pendientes (reservados)."""
    anio = int(anio or _dt.date.today().year)
    filas = _db.listar_vacaciones(id_empleado, id_empresa, anio=anio)
    disfrutados = sum(float(f.get("dias") or 0) for f in filas
                      if f.get("estado") in (APROBADA, CONSUMIDA))
    pendientes = sum(float(f.get("dias") or 0) for f in filas if f.get("estado") == PENDIENTE)
    asignados = float(dias_anuales)
    return {"anio": anio, "asignados": asignados,
            "disfrutados": round(disfrutados, 1), "pendientes": round(pendientes, 1),
            "disponibles": round(asignados - disfrutados - pendientes, 1)}


def _existe_solapamiento(id_empleado, id_empresa, fi, ff, anio, excluir_id=None) -> bool:
    for f in _db.listar_vacaciones(id_empleado, id_empresa, anio=anio):
        if f.get("estado") not in _ACTIVOS:
            continue
        if excluir_id and f.get("id") == excluir_id:
            continue
        if not f.get("fecha_inicio") or not f.get("fecha_fin"):
            continue
        if _solapa(fi, ff, _fecha(f["fecha_inicio"]), _fecha(f["fecha_fin"])):
            return True
    return False


# ── Solicitud ──────────────────────────────────────────────────────────────────
def solicitar(id_empleado, fecha_inicio, fecha_fin, id_empresa=None) -> int:
    """Crea una solicitud (estado PENDIENTE). Valida fechas, días y solapamiento.
    Devuelve el id; lanza GestionLaboralError si la validación falla."""
    fi, ff = _fecha(fecha_inicio), _fecha(fecha_fin)
    dias = _dias_naturales(fi, ff)
    if dias <= 0:
        raise GestionLaboralError("El número de días debe ser positivo.")
    anio = fi.year
    if _existe_solapamiento(id_empleado, id_empresa, fi, ff, anio):
        raise GestionLaboralError("Las fechas se solapan con otra solicitud/periodo de vacaciones.")
    vid = _db.crear_vacaciones(id_empleado, id_empresa, anio=anio, tipo="solicitud",
                               fecha_inicio=fi.isoformat(), fecha_fin=ff.isoformat(),
                               dias=dias, estado=PENDIENTE)
    if not vid:
        raise GestionLaboralError("No se pudo registrar la solicitud de vacaciones.")
    return vid


# ── Cambios de estado ────────────────────────────────────────────────────────
def _cambiar_estado(id_vac, nuevo, id_empresa=None, aprobado_por=None,
                    desde=None) -> bool:
    v = _db.obtener_vacaciones(id_vac, id_empresa)
    if not v:
        raise GestionLaboralError("Solicitud de vacaciones no encontrada.")
    if desde and v.get("estado") not in desde:
        raise GestionLaboralError(
            f"No se puede pasar a '{nuevo}' desde '{v.get('estado')}'.")
    campos = {"estado": nuevo}
    if aprobado_por is not None:
        campos["aprobado_por"] = aprobado_por
    return _db.actualizar_vacaciones(id_vac, id_empresa, **campos)


def aprobar(id_vac, usuario=None, id_empresa=None) -> bool:
    return _cambiar_estado(id_vac, APROBADA, id_empresa, aprobado_por=usuario, desde=(PENDIENTE,))


def denegar(id_vac, usuario=None, id_empresa=None) -> bool:
    return _cambiar_estado(id_vac, DENEGADA, id_empresa, aprobado_por=usuario, desde=(PENDIENTE,))


def cancelar(id_vac, usuario=None, id_empresa=None) -> bool:
    return _cambiar_estado(id_vac, CANCELADA, id_empresa, aprobado_por=usuario,
                           desde=(PENDIENTE, APROBADA))


def listar(id_empleado, id_empresa=None, anio=None) -> list:
    return _db.listar_vacaciones(id_empleado, id_empresa, anio=anio)
