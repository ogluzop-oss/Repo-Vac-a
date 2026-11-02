"""
Cuentas conectadas (OAuth) por plataforma social. Mismo patrón de cifrado que
`rrhh_empleados.iban`/`tesoreria.cuentas_bancarias` (petición explícita de seguridad en sesiones
previas): el token se cifra con `services.seguridad.secret_manager` (Fernet, rotación de claves)
antes de guardarse; nunca se expone en claro salvo al propio cliente de plataforma que lo necesita
para llamar a la API real.
"""

import logging

logger = logging.getLogger("redes_sociales.cuentas")

PLATAFORMAS = ("instagram", "facebook", "tiktok", "youtube", "x")
ESTADOS = ("desconectada", "conectada", "error", "expirada")


class CuentaError(Exception):
    pass


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def conectar(plataforma, *, id_externo, access_token, refresh_token=None, token_expira=None,
            nombre_cuenta=None, conectado_por=None, id_empresa=None) -> dict:
    """Da de alta (o reconecta) una cuenta. Los tokens llegan en claro desde el flujo OAuth del
    navegador/wizard de la GUI y se cifran aquí mismo antes de tocar disco/BD."""
    if plataforma not in PLATAFORMAS:
        raise CuentaError(f"Plataforma no soportada: {plataforma!r}")
    if not access_token:
        raise CuentaError("Falta el access_token.")
    id_empresa = _emp(id_empresa)
    from src.services.seguridad import secret_manager
    token_c = secret_manager.cifrar(access_token)
    refresh_c = secret_manager.cifrar(refresh_token) if refresh_token else None
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM redes_sociales_cuentas WHERE id_empresa=%s AND plataforma=%s "
                "AND id_externo=%s", (id_empresa, plataforma, id_externo))
            existente = cur.fetchone()
            if existente:
                cur.execute(
                    "UPDATE redes_sociales_cuentas SET access_token=%s, refresh_token=%s, "
                    "token_expira=%s, nombre_cuenta=%s, estado='conectada', ultimo_error=NULL, "
                    "conectado_por=%s, fecha_conexion=NOW() WHERE id=%s",
                    (token_c, refresh_c, token_expira, nombre_cuenta, conectado_por, existente[0]))
                id_cuenta = existente[0]
            else:
                cur.execute(
                    "INSERT INTO redes_sociales_cuentas (id_empresa, plataforma, nombre_cuenta, "
                    "id_externo, access_token, refresh_token, token_expira, estado, "
                    "conectado_por, fecha_conexion) VALUES (%s,%s,%s,%s,%s,%s,%s,'conectada',%s,NOW())",
                    (id_empresa, plataforma, nombre_cuenta, id_externo, token_c, refresh_c,
                     token_expira, conectado_por))
                id_cuenta = cur.lastrowid
    except CuentaError:
        raise
    except Exception as e:
        logger.error("conectar(%s): %s", plataforma, e)
        raise CuentaError("No se pudo guardar la conexión.") from e

    try:
        from src.services import eventos as _EV
        _EV.publicar("REDES_SOCIALES_CUENTA_CONECTADA", id_empresa=id_empresa,
                     origen="redes_sociales", ref_entidad="redes_sociales_cuenta",
                     ref_id=id_cuenta, payload={"plataforma": plataforma})
    except Exception:
        pass
    return {"ok": True, "id": id_cuenta}


def desconectar(id_cuenta, id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE redes_sociales_cuentas SET estado='desconectada', access_token=NULL, "
                "refresh_token=NULL WHERE id=%s AND id_empresa=%s", (id_cuenta, id_empresa))
            ok = cur.rowcount > 0
        return {"ok": ok}
    except Exception as e:
        logger.error("desconectar(%s): %s", id_cuenta, e)
        return {"ok": False, "error": "error_interno"}


def listar(*, plataforma=None, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if plataforma:
        filtros.append("plataforma=%s"); params.append(plataforma)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, id_empresa, plataforma, nombre_cuenta, id_externo, estado, "
                "ultimo_error, conectado_por, fecha_conexion, token_expira FROM "
                "redes_sociales_cuentas WHERE " + " AND ".join(filtros) + " ORDER BY plataforma",
                params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar: %s", e)
        return []


def obtener_token(id_cuenta, id_empresa=None) -> str | None:
    """Descifra y devuelve el access_token de una cuenta — SOLO para uso interno de los clientes
    de plataforma (`plataformas/*.py`), nunca se expone a la GUI ni a logs."""
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT access_token FROM redes_sociales_cuentas WHERE id=%s AND id_empresa=%s "
                "AND estado='conectada'", (id_cuenta, id_empresa))
            row = cur.fetchone()
        if not row or not row[0]:
            return None
        from src.services.seguridad import secret_manager
        return secret_manager.descifrar(row[0])
    except Exception as e:
        logger.error("obtener_token(%s): %s", id_cuenta, e)
        return None


def marcar_error(id_cuenta, motivo, id_empresa=None) -> None:
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE redes_sociales_cuentas SET estado='error', ultimo_error=%s "
                "WHERE id=%s AND id_empresa=%s", ((motivo or "")[:255], id_cuenta, id_empresa))
    except Exception as e:
        logger.error("marcar_error(%s): %s", id_cuenta, e)
