"""
Portal del Empleado (F4.10) — fachada de SOLO LECTURA sobre el ecosistema RRHH.

No duplica lógica ni crea tablas: agrega la información PROPIA del trabajador reutilizando
`empleados.expediente()`, `vacaciones_servicio`, `control_horario` y `rrhh_documentos`.
Seguridad: el acceso se resuelve por `id_usuario` (vínculo de la cuenta) → el trabajador
solo puede consultar SU expediente; nunca el de otros. Multiempresa por id_empresa.
"""

import datetime as _dt
import logging

logger = logging.getLogger("rrhh.portal")


class AccesoDenegado(Exception):
    """El usuario no tiene un expediente de empleado vinculado."""


def resolver_empleado(usuario, id_empresa=None) -> dict | None:
    """Devuelve el empleado vinculado a la cuenta `usuario` (por id_usuario)."""
    from src.rrhh.db import empleados
    if not isinstance(usuario, dict):
        return None
    return empleados.obtener_por_usuario(usuario.get("id"), id_empresa)


def panel(id_empleado, id_empresa=None) -> dict:
    """Vista propia del trabajador: personal + contratos + nóminas + vacaciones (con
    saldo) + ausencias + control horario (con totales) + documentos. SOLO LECTURA."""
    from src.rrhh.db import empleados
    from src.rrhh import control_horario, vacaciones_servicio
    exp = empleados.expediente(id_empleado, id_empresa)
    if not exp:
        raise AccesoDenegado("Empleado no encontrado.")
    e = exp["empleado"]
    personal = {k: e.get(k) for k in (
        "nombre", "apellidos", "nif", "email", "telefono", "id_centro", "categoria",
        "grupo_prof", "puesto", "convenio", "fecha_alta", "estado")}
    jornadas = exp.get("control_horario", [])
    return {
        "personal": personal,
        "contratos": exp.get("contratos", []),
        "nominas": exp.get("nominas", []),
        "vacaciones": {"saldo": vacaciones_servicio.saldo(id_empleado, id_empresa=id_empresa),
                       "lista": exp.get("vacaciones", [])},
        "ausencias": exp.get("ausencias", []),
        "control_horario": {"jornadas": jornadas, "totales": control_horario._totales(jornadas)},
        "documentos": exp.get("documentos", []),
        "documentos_pendientes": documentos_pendientes(id_empleado, id_empresa),
    }


def panel_de_usuario(usuario, id_empresa=None) -> dict:
    """Resuelve el empleado del usuario autenticado y devuelve SU panel. Garantiza que
    cada usuario solo ve su propia información."""
    emp = resolver_empleado(usuario, id_empresa)
    if not emp:
        raise AccesoDenegado("La cuenta no tiene un expediente de empleado vinculado.")
    return panel(emp["id"], id_empresa)


def documentos_pendientes(id_empleado, id_empresa=None) -> list:
    """Documentos del trabajador pendientes de firma/aceptación (solo propios)."""
    from src.rrhh import firma_servicio
    return firma_servicio.listar_pendientes(id_empleado, id_empresa)


def aceptar_documento(id_empleado, id_documento, usuario=None, ip=None, id_empresa=None) -> bool:
    """El trabajador acepta un documento PROPIO (seguridad por id_empleado)."""
    from src.rrhh import firma_servicio
    return firma_servicio.aceptar(id_documento, usuario=usuario, id_empleado=id_empleado,
                                  ip=ip, id_empresa=id_empresa)


def rechazar_documento(id_empleado, id_documento, usuario=None, ip=None, motivo=None,
                       id_empresa=None) -> bool:
    from src.rrhh import firma_servicio
    return firma_servicio.rechazar(id_documento, usuario=usuario, id_empleado=id_empleado,
                                   ip=ip, motivo=motivo, id_empresa=id_empresa)


def solicitar_vacaciones(id_empleado, fecha_inicio, fecha_fin, id_empresa=None) -> int:
    """El trabajador solicita vacaciones (reutiliza vacaciones_servicio; no duplica)."""
    from src.rrhh import vacaciones_servicio
    return vacaciones_servicio.solicitar(id_empleado, fecha_inicio, fecha_fin, id_empresa=id_empresa)


def exportar_control_horario(id_empleado, id_empresa=None, anio=None) -> str:
    """CSV del control horario propio (reutiliza control_horario, sin recalcular)."""
    from src.rrhh import control_horario
    desde = _dt.date(int(anio), 1, 1).isoformat() if anio else None
    hasta = _dt.date(int(anio), 12, 31).isoformat() if anio else None
    return control_horario.exportar_csv(
        control_horario.listar_jornadas(id_empleado, id_empresa, desde=desde, hasta=hasta))
