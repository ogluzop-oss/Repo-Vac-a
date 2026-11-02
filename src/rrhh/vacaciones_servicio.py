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
# Aprobación jerárquica en cascada (petición explícita, migr. 0322): si el empleado tiene un
# responsable directo asignado (`rrhh_empleados.id_responsable`), la solicitud pasa PRIMERO por
# él/ella y solo después por RRHH/admin (aprobación final); si NO tiene responsable, se mantiene
# el flujo de un solo paso de siempre (directo a `PENDIENTE` -> `APROBADA`/`DENEGADA`), cero
# cambio de comportamiento para empresas sin organigrama configurado.
PENDIENTE_RESPONSABLE, PENDIENTE_RRHH = "pend_resp", "pend_rrhh"
_PENDIENTES = (PENDIENTE, PENDIENTE_RESPONSABLE, PENDIENTE_RRHH)
_ACTIVOS = (PENDIENTE, PENDIENTE_RESPONSABLE, PENDIENTE_RRHH, APROBADA, CONSUMIDA)   # cuentan para saldo/solapamiento


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
    pendientes = sum(float(f.get("dias") or 0) for f in filas if f.get("estado") in _PENDIENTES)
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


def _tiene_responsable(id_empleado, id_empresa) -> bool:
    try:
        from src.rrhh.db import empleados as _EMP
        emp = _EMP.obtener_empleado(id_empleado, id_empresa)
        return bool(emp and emp.get("id_responsable"))
    except Exception as e:
        logger.warning("_tiene_responsable(%s): %s", id_empleado, e)
        return False


# ── Solicitud ──────────────────────────────────────────────────────────────────
def solicitar(id_empleado, fecha_inicio, fecha_fin, id_empresa=None) -> int:
    """Crea una solicitud. Si el empleado tiene un responsable directo asignado, arranca en
    `PENDIENTE_RESPONSABLE` (cascada); si no, en `PENDIENTE` (flujo de un solo paso, igual que
    siempre). Valida fechas, días y solapamiento. Devuelve el id; lanza GestionLaboralError si la
    validación falla."""
    fi, ff = _fecha(fecha_inicio), _fecha(fecha_fin)
    dias = _dias_naturales(fi, ff)
    if dias <= 0:
        raise GestionLaboralError("El número de días debe ser positivo.")
    anio = fi.year
    if _existe_solapamiento(id_empleado, id_empresa, fi, ff, anio):
        raise GestionLaboralError("Las fechas se solapan con otra solicitud/periodo de vacaciones.")
    estado_inicial = PENDIENTE_RESPONSABLE if _tiene_responsable(id_empleado, id_empresa) else PENDIENTE
    vid = _db.crear_vacaciones(id_empleado, id_empresa, anio=anio, tipo="solicitud",
                               fecha_inicio=fi.isoformat(), fecha_fin=ff.isoformat(),
                               dias=dias, estado=estado_inicial)
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
    """Aprobación de UN SOLO PASO — se mantiene tal cual para compatibilidad (llamadores que no
    pasan por la cascada); válida desde `PENDIENTE` o desde `PENDIENTE_RRHH` (último paso de la
    cascada, cuando el responsable ya dio su visto bueno)."""
    return _cambiar_estado(id_vac, APROBADA, id_empresa, aprobado_por=usuario,
                           desde=(PENDIENTE, PENDIENTE_RRHH))


def aprobar_responsable(id_vac, usuario=None, id_empresa=None) -> bool:
    """Primer paso de la cascada: el responsable directo da su visto bueno y la solicitud pasa a
    `PENDIENTE_RRHH` (aprobación final) — NO queda aprobada todavía. Guarda el aprobador de este
    paso en `aprobado_por_responsable`, dejando `aprobado_por` libre para el aprobador FINAL."""
    v = _db.obtener_vacaciones(id_vac, id_empresa)
    if not v:
        raise GestionLaboralError("Solicitud de vacaciones no encontrada.")
    if v.get("estado") != PENDIENTE_RESPONSABLE:
        raise GestionLaboralError(f"No se puede aprobar como responsable desde '{v.get('estado')}'.")
    return _db.actualizar_vacaciones(id_vac, id_empresa, estado=PENDIENTE_RRHH,
                                     aprobado_por_responsable=usuario)


def avanzar_aprobacion(id_vac, usuario=None, id_empresa=None) -> bool:
    """Punto de entrada ÚNICO para el botón "Aprobar" de la GUI (petición explícita de cascada):
    determina automáticamente el paso correcto según el estado actual — si está en
    `PENDIENTE_RESPONSABLE` avanza al siguiente nivel (RRHH); si está en `PENDIENTE`/
    `PENDIENTE_RRHH`, aprueba en firme. Así la interfaz no necesita un botón distinto por nivel ni
    saber si la empresa tiene organigrama configurado."""
    v = _db.obtener_vacaciones(id_vac, id_empresa)
    if not v:
        raise GestionLaboralError("Solicitud de vacaciones no encontrada.")
    if v.get("estado") == PENDIENTE_RESPONSABLE:
        return aprobar_responsable(id_vac, usuario=usuario, id_empresa=id_empresa)
    return aprobar(id_vac, usuario=usuario, id_empresa=id_empresa)


def denegar(id_vac, usuario=None, id_empresa=None) -> bool:
    """Denegar es válido en CUALQUIER paso pendiente de la cascada — un "no" del responsable o de
    RRHH cierra la solicitud igual, sin necesitar pasar por el resto de niveles."""
    return _cambiar_estado(id_vac, DENEGADA, id_empresa, aprobado_por=usuario, desde=_PENDIENTES)


def cancelar(id_vac, usuario=None, id_empresa=None) -> bool:
    return _cambiar_estado(id_vac, CANCELADA, id_empresa, aprobado_por=usuario,
                           desde=(*_PENDIENTES, APROBADA))


def listar(id_empleado, id_empresa=None, anio=None) -> list:
    return _db.listar_vacaciones(id_empleado, id_empresa, anio=anio)


# ── Sincronización automática desde la rejilla de Horarios ─────────────────────
# Origen distinto de "solicitud" (creada por `solicitar()`/aprobada por `aprobar()` desde el
# diálogo "Vacaciones y ausencias"): un día marcado como VACACIONES directamente en la rejilla
# de Horarios (`gui/horarios_gui.py` → `rrhh/horarios_vinculo_empleado.sincronizar_vacaciones_horario`)
# es una decisión YA TOMADA por el admin/SUPERADMIN al guardar el horario — no pasa por el flujo
# de solicitud/aprobación, se registra directamente como CONSUMIDA (cuenta igual que APROBADA
# para `saldo()`, ver arriba).
TIPO_HORARIO = "horario"


def sincronizar_dias_horario(id_empleado, dias_marcados, fecha_inicio_semana, fecha_fin_semana,
                             id_empresa=None) -> None:
    """Sincroniza, dentro de UNA semana de la rejilla de Horarios `[fecha_inicio_semana,
    fecha_fin_semana]` (ambas `date`, inclusive), los días de VACACIONES marcados para
    `id_empleado` contra `rrhh_vacaciones` — la MISMA tabla que usa el diálogo "Vacaciones y
    ausencias" (`GestionLaboralDialog`) y que lee `vacaciones_servicio.saldo()`/`finiquito_servicio`;
    nunca un mecanismo paralelo. Un registro POR DÍA (`tipo=TIPO_HORARIO`, `estado=CONSUMIDA`).

    `dias_marcados`: iterable de `date` (subconjunto de los 7 días de la semana) actualmente
    marcados en la rejilla para este empleado. Idempotente: volver a llamar con el MISMO conjunto
    no inserta ni borra nada. Si un día deja de estar en `dias_marcados` (se des-marcó en la
    rejilla), el registro `tipo=TIPO_HORARIO` correspondiente se ELIMINA — no queda un
    `rrhh_vacaciones` fantasma. Solo toca registros `tipo=TIPO_HORARIO` de ESTA semana: nunca una
    solicitud manual (`tipo='solicitud'`), que sigue su propio ciclo de aprobación."""
    existentes = {}
    for f in _db.listar_vacaciones(id_empleado, id_empresa):
        if f.get("tipo") != TIPO_HORARIO:
            continue
        fi, ff = f.get("fecha_inicio"), f.get("fecha_fin")
        if not fi or fi != ff:
            continue
        try:
            d = _fecha(fi)
        except GestionLaboralError:
            continue
        if fecha_inicio_semana <= d <= fecha_fin_semana:
            existentes[d] = f.get("id")

    deseados = {d for d in (dias_marcados or set())
                if fecha_inicio_semana <= d <= fecha_fin_semana}

    for dia in deseados - existentes.keys():
        _db.crear_vacaciones(id_empleado, id_empresa, anio=dia.year, tipo=TIPO_HORARIO,
                             fecha_inicio=dia.isoformat(), fecha_fin=dia.isoformat(),
                             dias=1, estado=CONSUMIDA)
    for dia, vid in existentes.items():
        if dia not in deseados:
            _db.eliminar_vacaciones(vid, id_empresa)
