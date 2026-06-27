"""
Infraestructura común AEAT — persistencia de declaraciones (FASE AEAT-1).

CRUD de aeat_declaraciones + aeat_declaracion_lineas, idempotente por
(id_empresa, modelo, ejercicio, periodo) en estado no anulado, con hash documental sobre las
casillas y traza en auditoria_logs. Reutilizable por cualquier modelo (303 y futuros).
"""

import datetime as _dt
import hashlib
import json
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion
from src.services.aeat import estados as E

logger = logging.getLogger("aeat.base")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def hash_casillas(modelo, ejercicio, periodo, casillas) -> str:
    """Hash documental SHA-256 sobre el contenido fiscal (modelo+periodo+casillas)."""
    base = json.dumps({"modelo": modelo, "ejercicio": ejercicio, "periodo": periodo,
                       "casillas": [(c["casilla"], round(float(c["importe"]), 2)) for c in casillas]},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def declaracion_vigente(modelo, ejercicio, periodo, id_empresa=None) -> dict | None:
    """Declaración NO anulada para la clave (idempotencia). None si no hay."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM aeat_declaraciones WHERE id_empresa=%s AND modelo=%s "
                        "AND ejercicio=%s AND periodo=%s AND estado<>%s ORDER BY id DESC LIMIT 1",
                        (id_empresa, modelo, int(ejercicio), periodo, E.ANULADO))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("declaracion_vigente: %s", e)
        return None


def guardar_declaracion(modelo, ejercicio, periodo, resultado, casillas, *,
                        observaciones=None, usuario=None, id_empresa=None) -> int | None:
    """Crea/regenera (idempotente) una declaración en estado GENERADO con sus casillas.

    Si ya existe una BORRADOR/GENERADO para la clave, la regenera (reemplaza casillas). Si está
    PRESENTADA, NO la sobreescribe (devuelve None). Calcula el hash documental y audita."""
    id_empresa = _emp(id_empresa)
    _exigir_permiso("aeat.generar")
    h = hash_casillas(modelo, ejercicio, periodo, casillas)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, estado FROM aeat_declaraciones WHERE id_empresa=%s AND modelo=%s "
                        "AND ejercicio=%s AND periodo=%s AND estado<>%s ORDER BY id DESC LIMIT 1 "
                        "FOR UPDATE", (id_empresa, modelo, int(ejercicio), periodo, E.ANULADO))
            ex = cur.fetchone()
            if ex:
                d = _fila(cur, ex)
                if d["estado"] == E.PRESENTADO:
                    logger.info("guardar_declaracion: %s %s/%s ya PRESENTADA; no se sobreescribe",
                                modelo, ejercicio, periodo)
                    return None
                did = d["id"]
                cur.execute("UPDATE aeat_declaraciones SET estado=%s, resultado=%s, hash=%s, "
                            "fecha_generacion=NOW(), observaciones=%s WHERE id=%s",
                            (E.GENERADO, round(float(resultado), 2), h, observaciones, did))
                cur.execute("DELETE FROM aeat_declaracion_lineas WHERE id_declaracion=%s", (did,))
            else:
                cur.execute("INSERT INTO aeat_declaraciones (id_empresa, modelo, ejercicio, periodo, "
                            "estado, resultado, hash, observaciones) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (id_empresa, modelo, int(ejercicio), periodo, E.GENERADO,
                             round(float(resultado), 2), h, observaciones))
                did = cur.lastrowid
            for c in casillas:
                cur.execute("INSERT INTO aeat_declaracion_lineas (id_declaracion, casilla, "
                            "descripcion, importe) VALUES (%s,%s,%s,%s)",
                            (did, str(c["casilla"]), c.get("descripcion"),
                             round(float(c["importe"]), 2)))
            conn.commit()
        _audit(usuario, f"AEAT_{modelo}_GENERADO", f"decl={did} {ejercicio}/{periodo} res={resultado}")
        return did
    except Exception as e:
        logger.error("guardar_declaracion: %s", e)
        return None


def obtener_declaracion(id_declaracion, *, con_lineas=True, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM aeat_declaraciones WHERE id=%s AND id_empresa=%s",
                        (id_declaracion, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            d = _fila(cur, r)
            if con_lineas:
                cur.execute("SELECT casilla, descripcion, importe FROM aeat_declaracion_lineas "
                            "WHERE id_declaracion=%s ORDER BY id", (id_declaracion,))
                d["casillas"] = [_fila(cur, x) for x in cur.fetchall()]
            return d
    except Exception as e:
        logger.error("obtener_declaracion: %s", e)
        return None


def listar_declaraciones(*, modelo=None, ejercicio=None, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM aeat_declaraciones WHERE id_empresa=%s"
    p = [id_empresa]
    if modelo:
        q += " AND modelo=%s"; p.append(modelo)
    if ejercicio:
        q += " AND ejercicio=%s"; p.append(int(ejercicio))
    q += " ORDER BY ejercicio DESC, periodo DESC, id DESC"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_declaraciones: %s", e)
        return []


def cambiar_estado(id_declaracion, nuevo, *, usuario=None, id_empresa=None) -> bool:
    """Transición validada (BORRADOR/GENERADO→PRESENTADO/ANULADO). Audita la acción."""
    id_empresa = _emp(id_empresa)
    if nuevo not in E.ESTADOS:
        raise ValueError(f"estado inválido: {nuevo}")
    d = obtener_declaracion(id_declaracion, con_lineas=False, id_empresa=id_empresa)
    if not d:
        return False
    if not E.transicion_valida(d["estado"], nuevo):
        raise ValueError(f"transición no permitida: {d['estado']} → {nuevo}")
    if nuevo == E.PRESENTADO:
        _exigir_permiso("aeat.presentar")
    sets = "estado=%s"
    params = [nuevo]
    if nuevo == E.PRESENTADO:
        sets += ", fecha_presentacion=NOW()"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE aeat_declaraciones SET {sets} WHERE id=%s AND id_empresa=%s",
                        (*params, id_declaracion, id_empresa))
            conn.commit()
        _audit(usuario, f"AEAT_{d['modelo']}_{nuevo}", f"decl={id_declaracion}")
        return True
    except Exception as e:
        logger.error("cambiar_estado: %s", e)
        return False


def guardar_fichero(id_declaracion, ruta, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE aeat_declaraciones SET fichero_generado=%s WHERE id=%s AND id_empresa=%s",
                        (ruta, id_declaracion, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_fichero: %s", e)
        return False


def _audit(usuario, accion, detalles):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria(usuario or "sistema", accion, "aeat_declaraciones", detalles)
    except Exception as e:
        logger.debug("audit %s: %s", accion, e)


def _exigir_permiso(permiso):
    """Guard RBAC (FASE 9): sin sesión activa no bloquea (flujos internos); con usuario sin
    permiso lanza ErrorAutorizacion. Best-effort si el motor no está disponible."""
    try:
        from src.services import autorizacion
        autorizacion.exigir(None, permiso)
    except ImportError:
        pass
