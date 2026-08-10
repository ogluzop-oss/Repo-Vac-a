"""
Orquestación multi-terminal de la grabación (videovigilancia). En un despliegue con VARIAS terminales
(PDA/PC) de la misma empresa, garantiza que EXACTAMENTE UNA graba cada cámara — evita ficheros duplicados,
colisiones sobre el fichero del día y CPU desperdiciada. Con FAILOVER: si la terminal propietaria cae, su
concesión (lease) caduca y otra la reclama.

Mecanismo: una CONCESIÓN por cámara (`camaras_grabador`, UNIQUE por id_camara) con `terminal` propietaria y
`expira`. La terminal renueva (heartbeat) las suyas; reclama las libres o caducadas. Aislamiento por empresa.
Reutiliza la identidad de terminal existente (`TERMINAL_CODIGO`), sin motores ni tablas paralelas.
"""

import datetime as _dt
import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("camaras.orquestacion")

TTL_SEG = 120        # duración de la concesión; se renueva a la mitad (heartbeat)


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def terminal_id() -> str:
    """Identidad ESTABLE de esta terminal: `TERMINAL_CODIGO`/`TERMINAL_CODE` de configuración o, en su
    defecto, nombre de host + MAC (única por máquina). Reutiliza la convención de identidad operativa."""
    import os
    for k in ("TERMINAL_CODIGO", "TERMINAL_CODE", "TERMINAL_ID"):
        v = os.getenv(k)
        if v and v.strip():
            return v.strip()
    import platform
    import uuid
    try:
        return f"{platform.node() or 'terminal'}-{uuid.getnode():012x}"
    except Exception:
        return platform.node() or "terminal"


def reclamar(id_camara, *, terminal=None, id_empresa=None, ttl_seg=TTL_SEG) -> bool:
    """Intenta que esta terminal quede a cargo de grabar `id_camara`. ATÓMICO: solo lo consigue si la cámara
    está libre, su concesión caducó, o ya era suya (la renueva). Devuelve True si queda a su cargo."""
    terminal = terminal or terminal_id()
    id_empresa = _emp(id_empresa)
    if not id_camara or not id_empresa:
        return False
    ahora = _dt.datetime.now()
    nueva = ahora + _dt.timedelta(seconds=int(ttl_seg))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT terminal, expira FROM camaras_grabador WHERE id_camara=%s FOR UPDATE",
                        (id_camara,))
            row = cur.fetchone()
            if row is None:
                # nadie la tiene → la reclamo. UNIQUE(id_camara) impide que dos terminales la inserten a la vez.
                cur.execute("INSERT INTO camaras_grabador (id_empresa, id_camara, terminal, expira) "
                            "VALUES (%s,%s,%s,%s)", (id_empresa, id_camara, terminal, nueva))
                conn.commit()
                return True
            dueno = row[0] if not isinstance(row, dict) else row["terminal"]
            expira = row[1] if not isinstance(row, dict) else row["expira"]
            if dueno == terminal or (expira and expira < ahora):
                cur.execute("UPDATE camaras_grabador SET terminal=%s, expira=%s, actualizado=NOW() "
                            "WHERE id_camara=%s", (terminal, nueva, id_camara))
                conn.commit()
                return True
            conn.commit()
            return False            # de otra terminal viva
    except Exception as e:
        logger.debug("reclamar(%s): %s", id_camara, e)
        return False


def renovar(*, terminal=None, id_empresa=None, ttl_seg=TTL_SEG) -> int:
    """Heartbeat: prolonga la concesión de TODAS las cámaras a cargo de esta terminal. Devuelve cuántas."""
    terminal = terminal or terminal_id()
    id_empresa = _emp(id_empresa)
    nueva = _dt.datetime.now() + _dt.timedelta(seconds=int(ttl_seg))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE camaras_grabador SET expira=%s, actualizado=NOW() WHERE terminal=%s AND "
                        "id_empresa<=>%s", (nueva, terminal, id_empresa))
            conn.commit()
            return cur.rowcount
    except Exception as e:
        logger.debug("renovar: %s", e)
        return 0


def liberar(id_camara=None, *, terminal=None, id_empresa=None) -> int:
    """Libera concesiones de esta terminal (al parar/ceder). Si `id_camara`, solo esa; si no, todas las suyas."""
    terminal = terminal or terminal_id()
    id_empresa = _emp(id_empresa)
    q = "DELETE FROM camaras_grabador WHERE terminal=%s AND id_empresa<=>%s"
    p = [terminal, id_empresa]
    if id_camara is not None:
        q += " AND id_camara=%s"
        p.append(id_camara)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, tuple(p))
            conn.commit()
            return cur.rowcount
    except Exception as e:
        logger.debug("liberar: %s", e)
        return 0


def propietario(id_camara) -> str | None:
    """Terminal que tiene a cargo la cámara (con concesión VIGENTE), o None si está libre/caducada."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT terminal FROM camaras_grabador WHERE id_camara=%s AND expira>=NOW()",
                        (id_camara,))
            row = cur.fetchone()
            if not row:
                return None
            return row[0] if not isinstance(row, dict) else row["terminal"]
    except Exception as e:
        logger.debug("propietario(%s): %s", id_camara, e)
        return None


def a_cargo_de(*, terminal=None, id_empresa=None) -> list:
    """Ids de cámara que esta terminal tiene a cargo con concesión vigente."""
    terminal = terminal or terminal_id()
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_camara FROM camaras_grabador WHERE terminal=%s AND id_empresa<=>%s AND "
                        "expira>=NOW()", (terminal, id_empresa))
            return [(r[0] if not isinstance(r, dict) else r["id_camara"]) for r in cur.fetchall()]
    except Exception as e:
        logger.debug("a_cargo_de: %s", e)
        return []
