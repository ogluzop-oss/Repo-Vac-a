"""
Traspasos logísticos (Ajuste post-lanzamiento · Módulo 8) — capa fina para la REST API. Delega 100% en
`db.logistica`, que ya implementa el modelo real (documento cabecera + palés + líneas por artículo).

`centro_receptor`/`origen` en móvil se resuelven SIEMPRE desde `usuario["id_tienda"]` (el código de
tienda/almacén ya viene en el JWT, ver `api/security.py::_jwt_contexto`) — nunca de un selector manual,
para que "recepción"/"traspaso" usen automáticamente el centro asociado al perfil del empleado.
"""


def listar(id_empresa, id_tienda=None, *, estado="ABIERTOS", texto="", limite=50) -> list[dict]:
    from src.db import logistica
    filas = logistica.obtener_historial_traspasos(
        estado, texto, id_empresa=id_empresa, id_tienda=id_tienda)
    return filas[:limite]


def detalle(id_documento, id_empresa, id_tienda=None) -> dict | None:
    from src.db import logistica
    maestro, detalles = logistica.obtener_documento_logistico_completo(
        id_documento, id_empresa=id_empresa, id_tienda=id_tienda)
    if not maestro:
        return None
    return {**maestro, "lineas": detalles}


def crear(id_empresa, id_tienda_origen, usuario_nombre, destino, agencia, observaciones,
         pales: dict) -> dict | None:
    """`id_tienda_origen` es el código de tienda/almacén del usuario (ya el `origen` real)."""
    from src.db import logistica
    if not id_tienda_origen:
        return None
    return logistica.guardar_traspaso_logistico(
        id_tienda_origen, destino, usuario_nombre, agencia, observaciones, pales,
        id_empresa=id_empresa, id_tienda=None)


def items_esperados(id_pale, id_empresa, id_tienda=None) -> list[dict]:
    from src.db import logistica
    return logistica.obtener_items_pale_traspaso(id_pale, id_empresa=id_empresa, id_tienda=id_tienda)


def recibir(id_pale, centro_receptor, usuario_nombre, items, id_empresa, id_tienda=None) -> dict:
    from src.db import logistica
    if not centro_receptor:
        return {"ok": False, "motivo": "sin_centro_receptor"}
    return logistica.procesar_recepcion_logistica(
        id_pale, centro_receptor, usuario_nombre, items, id_empresa=id_empresa, id_tienda=id_tienda)


def marcar_picking(id_documento, id_linea, pickeado, id_empresa, id_tienda=None) -> bool:
    from src.db import logistica
    return logistica.marcar_linea_picking(
        id_documento, id_linea, pickeado, id_empresa=id_empresa, id_tienda=id_tienda)


def confirmar_picking(id_documento, usuario_nombre, id_empresa, id_tienda=None) -> dict:
    from src.db import logistica
    return logistica.confirmar_picking_y_expedir(
        id_documento, usuario_nombre, id_empresa=id_empresa, id_tienda=id_tienda)


def listar_incidencias(id_empresa, estado=None, texto="") -> list[dict]:
    from src.db import logistica
    return logistica.listar_incidencias(estado, texto, id_empresa=id_empresa)


def crear_incidencia(id_empresa, id_documento, tipo, descripcion, usuario_nombre,
                     id_pale=None, codigo=None, cantidad=0) -> int | None:
    from src.db import logistica
    return logistica.registrar_incidencia(
        id_documento, tipo, descripcion, usuario_nombre,
        id_pale=id_pale, codigo=codigo, cantidad=cantidad, id_empresa=id_empresa)


def cerrar_incidencia(id_empresa, id_incidencia) -> bool:
    from src.db import logistica
    return logistica.cerrar_incidencia(id_incidencia, id_empresa=id_empresa)
