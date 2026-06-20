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
              id_empresa=None) -> int:
    """Alta de ausencia. Valida tipo, fechas, días y solapamiento incompatible."""
    if tipo not in TIPOS:
        raise GestionLaboralError(f"Tipo de ausencia no válido: {tipo!r}.")
    fi, ff = _fecha(fecha_inicio), _fecha(fecha_fin)
    dias = _dias_naturales(fi, ff)
    if _existe_solapamiento(id_empleado, id_empresa, fi, ff):
        raise GestionLaboralError("Las fechas se solapan con otra ausencia registrada.")
    aid = _db.crear_ausencia(id_empleado, id_empresa, tipo=tipo, fecha_inicio=fi.isoformat(),
                             fecha_fin=ff.isoformat(), dias=dias, motivo=motivo,
                             justificada=1 if justificada else 0)
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
