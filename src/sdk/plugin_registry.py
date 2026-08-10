"""Plugin Registry (Fase III · B4) — plugins instalados (persistencia + estado). Multiempresa."""

import json
import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("sdk.registry")


def _emp(id_empresa=None):
    return id_empresa   # NULL = plugin global


def instalar(clave, manifest, *, ruta=None, id_empresa=None, usuario=None) -> bool:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO plugins_instalados (id_empresa, clave, nombre, version, autor, estado, "
                "manifest, ruta, usuario) VALUES (%s,%s,%s,%s,%s,'instalado',%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), version=VALUES(version), "
                "estado='instalado', manifest=VALUES(manifest), ruta=VALUES(ruta), actualizado=NOW()",
                (id_empresa, clave, manifest.get("nombre"), manifest.get("version"),
                 manifest.get("autor"), json.dumps(manifest), ruta, usuario))
            conn.commit()
        try:
            from src.services import eventbus
            eventbus.publish("PluginInstalled", id_empresa=id_empresa, ref_entidad="plugin",
                             ref_id=clave, payload={"version": manifest.get("version")})
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error("instalar(%s): %s", clave, e)
        return False


def desinstalar(clave, *, id_empresa=None) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE plugins_instalados SET estado='eliminado', actualizado=NOW() WHERE "
                        "clave=%s AND (id_empresa=%s OR (%s IS NULL AND id_empresa IS NULL))",
                        (clave, id_empresa, id_empresa))
            conn.commit()
        # Desinstalación segura: retirar sus contribuciones.
        from src.sdk import extension_points, hooks
        extension_points.limpiar_plugin(clave); hooks.limpiar_plugin(clave)
        try:
            from src.services import eventbus
            eventbus.publish("PluginRemoved", id_empresa=id_empresa, ref_entidad="plugin", ref_id=clave)
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error("desinstalar(%s): %s", clave, e)
        return False


def listar_instalados(id_empresa=None, *, estado="instalado") -> list:
    q = "SELECT * FROM plugins_instalados WHERE (id_empresa=%s OR id_empresa IS NULL)"
    p = [id_empresa]
    if estado:
        q += " AND estado=%s"; p.append(estado)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_instalados: %s", e)
        return []
