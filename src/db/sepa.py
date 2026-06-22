"""
SEPA — persistencia (rama Tesorería, FASE 9).

Mandatos de adeudo (IBAN del deudor cifrado en reposo), remesas (transferencias pain.001 /
adeudos pain.008) y sus líneas. La generación de XML y validación XSD están en
src/services/tesoreria/sepa.py.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion
from src.utils import iban as _iban

logger = logging.getLogger("sepa_db")

ESTADOS_REMESA = ("borrador", "emitida", "aceptada", "rechazada", "ejecutada")
TIPOS_REMESA = ("TRANSFER", "ADEUDO")


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


# ─────────────────────────────── Mandatos ───────────────────────────────
def crear_mandato(referencia_mandato, nombre_deudor, iban_deudor, *, tipo="CORE", bic=None,
                  fecha_firma=None, id_empresa=None) -> int | None:
    """Alta de mandato de adeudo. Valida y cifra el IBAN del deudor."""
    id_empresa = _emp(id_empresa)
    iban_norm = _iban.normalizar_iban(iban_deudor)
    if not _iban.validar_iban(iban_norm):
        raise ValueError(f"IBAN de mandato inválido: {iban_deudor}")
    from src.utils import cripto
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM mandatos_sepa WHERE id_empresa=%s AND referencia_mandato=%s",
                        (id_empresa, referencia_mandato))
            ya = cur.fetchone()
            if ya:
                return ya[0] if not isinstance(ya, dict) else list(ya.values())[0]
            cur.execute(
                "INSERT INTO mandatos_sepa (id_empresa, referencia_mandato, tipo, nombre_deudor, "
                "iban_deudor, iban_mascara, bic, fecha_firma) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, referencia_mandato, tipo, nombre_deudor,
                 cripto.cifrar(iban_norm), _iban.mascara_iban(iban_norm),
                 (bic or "").upper() or None, fecha_firma))
            mid = cur.lastrowid
            conn.commit()
        _audit("alta_mandato_sepa", f"id={mid} ref={referencia_mandato}")
        return mid
    except ValueError:
        raise
    except Exception as e:
        logger.error("crear_mandato: %s", e)
        return None


def obtener_mandato(id_mandato, *, descifrar=False, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM mandatos_sepa WHERE id=%s AND id_empresa=%s",
                        (id_mandato, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            d = _fila(cur, r)
            if descifrar:
                from src.utils import cripto
                d["iban_deudor"] = cripto.descifrar_seguro(d["iban_deudor"]) or ""
            else:
                d["iban_deudor"] = d.get("iban_mascara")
            return d
    except Exception as e:
        logger.error("obtener_mandato: %s", e)
        return None


def listar_mandatos(*, solo_activos=True, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM mandatos_sepa WHERE id_empresa=%s"
    p = [id_empresa]
    if solo_activos:
        q += " AND estado='activo'"
    q += " ORDER BY id DESC"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            out = []
            for r in cur.fetchall():
                d = _fila(cur, r)
                d["iban_deudor"] = d.get("iban_mascara")
                out.append(d)
            return out
    except Exception as e:
        logger.error("listar_mandatos: %s", e)
        return []


# ─────────────────────────────── Remesas ───────────────────────────────
def crear_remesa(tipo, *, id_cuenta=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    tipo = (tipo or "").upper()
    if tipo not in TIPOS_REMESA:
        raise ValueError(f"tipo de remesa inválido: {tipo}")
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO remesas_sepa (id_empresa, tipo, estado, id_cuenta) "
                        "VALUES (%s,%s,'borrador',%s)", (id_empresa, tipo, id_cuenta))
            rid = cur.lastrowid
            conn.commit()
        _audit("crea_remesa", f"id={rid} {tipo}")
        return rid
    except ValueError:
        raise
    except Exception as e:
        logger.error("crear_remesa: %s", e)
        return None


def anadir_operacion(id_remesa, nombre_tercero, iban, importe, *, concepto=None, bic=None,
                     end_to_end_id=None, id_mandato=None, id_vencimiento=None,
                     id_empresa=None) -> int | None:
    """Añade una operación a una remesa (en borrador). Valida el IBAN del tercero."""
    id_empresa = _emp(id_empresa)
    iban_norm = _iban.normalizar_iban(iban)
    if not _iban.validar_iban(iban_norm):
        raise ValueError(f"IBAN inválido en operación: {iban}")
    import uuid
    e2e = end_to_end_id or ("E2E" + uuid.uuid4().hex[:20])
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT estado FROM remesas_sepa WHERE id=%s AND id_empresa=%s",
                        (id_remesa, id_empresa))
            r = cur.fetchone()
            if not r or (r[0] if not isinstance(r, dict) else list(r.values())[0]) != "borrador":
                raise ValueError("La remesa no está en borrador")
            cur.execute(
                "INSERT INTO remesa_lineas (id_empresa, id_remesa, nombre_tercero, iban, bic, "
                "importe, concepto, end_to_end_id, id_mandato, id_vencimiento) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_remesa, nombre_tercero, iban_norm, (bic or "").upper() or None,
                 round(float(importe or 0), 2), concepto, e2e, id_mandato, id_vencimiento))
            lid = cur.lastrowid
            cur.execute("UPDATE remesas_sepa SET num_operaciones=num_operaciones+1, "
                        "importe_total=importe_total+%s WHERE id=%s AND id_empresa=%s",
                        (round(float(importe or 0), 2), id_remesa, id_empresa))
            conn.commit()
        return lid
    except ValueError:
        raise
    except Exception as e:
        logger.error("anadir_operacion: %s", e)
        return None


def lineas_remesa(id_remesa, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM remesa_lineas WHERE id_remesa=%s AND id_empresa=%s ORDER BY id",
                        (id_remesa, id_empresa))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("lineas_remesa: %s", e)
        return []


def obtener_remesa(id_remesa, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM remesas_sepa WHERE id=%s AND id_empresa=%s",
                        (id_remesa, id_empresa))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("obtener_remesa: %s", e)
        return None


def guardar_xml(id_remesa, mensaje_id, xml_texto, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE remesas_sepa SET fichero_xml=%s, mensaje_id=%s, estado='emitida' "
                        "WHERE id=%s AND id_empresa=%s", (xml_texto, mensaje_id, id_remesa, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_xml: %s", e)
        return False


# Máquina de estados de remesa (transiciones permitidas). 'ejecutada' es terminal.
_TRANSICIONES = {
    "borrador": {"emitida"},
    "emitida": {"aceptada", "rechazada"},
    "aceptada": {"ejecutada", "rechazada"},
    "rechazada": {"borrador", "emitida"},
    "ejecutada": set(),
}


def cambiar_estado(id_remesa, estado, *, fecha_ejecucion=None, id_empresa=None) -> bool:
    """Transición de estado de la remesa, validando que sea legal (borrador→emitida→
    aceptada→ejecutada; rechazada reabre). Impide ejecución múltiple y retrocesos."""
    id_empresa = _emp(id_empresa)
    if estado not in ESTADOS_REMESA:
        raise ValueError(f"estado inválido: {estado}")
    actual = (obtener_remesa(id_remesa, id_empresa) or {}).get("estado")
    if actual is not None and estado not in _TRANSICIONES.get(actual, set()):
        raise ValueError(f"transición no permitida: {actual} → {estado}")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if fecha_ejecucion:
                cur.execute("UPDATE remesas_sepa SET estado=%s, fecha_ejecucion=%s "
                            "WHERE id=%s AND id_empresa=%s", (estado, fecha_ejecucion, id_remesa, id_empresa))
            else:
                cur.execute("UPDATE remesas_sepa SET estado=%s WHERE id=%s AND id_empresa=%s",
                            (estado, id_remesa, id_empresa))
            conn.commit()
        _audit("estado_remesa", f"id={id_remesa} → {estado}")
        return True
    except ValueError:
        raise
    except Exception as e:
        logger.error("cambiar_estado: %s", e)
        return False


def _audit(accion, detalles):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("sistema", accion, "remesas_sepa", detalles)
    except Exception as e:
        logger.debug("audit %s: %s", accion, e)
