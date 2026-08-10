"""
Gobierno para la IA (Paquete Enterprise 7, SUBFASE 7.9). El Copiloto y los Agentes conocen la
jerarquia, los responsables, las delegaciones, la cadena de mando y la autoridad ANTES de
responder. Permite respuestas como: "No puedo aprobar esa factura porque corresponde al Director
Financiero". Reutiliza responsables/delegacion/autoridad/aprobaciones.
"""

from src.services.gobierno import aprobaciones as _AP
from src.services.gobierno import autoridad as _AU
from src.services.gobierno import delegacion as _D
from src.services.gobierno import responsables as _R

_ORDEN = {"suplente": 1, "auditor": 2, "principal": 2, "supervisor": 3, "director": 4,
          "administrador": 5}
_ETIQUETA = {"principal": "Responsable", "supervisor": "Supervisor", "director": "Director",
             "administrador": "Administrador", "auditor": "Auditor", "suplente": "Suplente"}


def _emp(id_empresa=None):
    from src.services.gobierno import organigrama as _O
    return _O._emp(id_empresa)


def rol_org_efectivo(usuario, perfil=None, id_empresa=None) -> str:
    emp = _emp(id_empresa)
    # Rol efectivo = el MAYOR entre el rol organico asignado y el rol del perfil del ERP
    # (un ADMINISTRADOR no pierde autoridad por estar asignado a un nodo con rol inferior).
    roles = [x["rol_org"] for x in _R.nodos_de_usuario(usuario, emp)]
    roles.append(_AU.rol_org_de_perfil(perfil))
    rol = max(roles, key=lambda r: _ORDEN.get(r, 0))
    # SUBFASE 7.4: si sustituye a un responsable ausente, asume su autoridad (>= director).
    if _D.sustituye_a(usuario, emp) and _ORDEN.get(rol, 0) < _ORDEN["director"]:
        rol = "director"
    return rol


def contexto(usuario, id_empresa=None, perfil=None) -> dict:
    emp = _emp(id_empresa)
    rol = rol_org_efectivo(usuario, perfil, emp)
    return {"usuario": usuario, "rol_org": rol, "permisos": sorted(_AU.permisos_de(rol)),
            "nodos": _R.nodos_de_usuario(usuario, emp), "sustituye_a": _D.sustituye_a(usuario, emp)}


def puede_aprobar(usuario, entidad, importe=0, id_empresa=None, perfil=None) -> dict:
    emp = _emp(id_empresa)
    rol = rol_org_efectivo(usuario, perfil, emp)
    if not _AU.puede(rol, "aprobar"):
        return {"permitido": False, "rol": rol,
                "motivo": f"Tu rol ({_ETIQUETA.get(rol, rol)}) no tiene autoridad para aprobar."}
    regla = _AP.cadena_para(entidad, importe, emp)
    if not regla or not regla.get("cadena"):
        return {"permitido": True, "rol": rol, "motivo": "Autorizado por tu rol (sin cadena especifica)."}
    cadena = regla["cadena"]
    requerido = max(cadena, key=lambda r: _ORDEN.get(r, 0))
    if _ORDEN.get(rol, 0) >= _ORDEN.get(requerido, 0):
        return {"permitido": True, "rol": rol, "cadena": cadena,
                "motivo": f"Autorizado (cadena {regla['codigo']})."}
    return {"permitido": False, "rol": rol, "cadena": cadena, "requerido": requerido,
            "motivo": f"No puedo aprobar: corresponde al {_ETIQUETA.get(requerido, requerido)} "
                      f"(cadena {regla['codigo']} para {entidad} de {importe})."}
