"""
Asientos contables (E6.2) — alta con cuadre, diario, inmutabilidad y contraasiento.

Doble partida (Σ debe = Σ haber). Numeración correlativa por empresa+ejercicio.
Asiento `contabilizado` = inmutable (corrección solo por contraasiento). Ejercicio
cerrado = bloqueado. Hash de auditoría encadenado por empresa+ejercicio. Atómico.
"""

import datetime as _dt
import hashlib
import json
import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _fila_a_dict, _filas_a_dicts,
                             obtener_conexion, transaccion)
from src.services.contabilidad import cuentas as K

logger = logging.getLogger("contab.asientos")

_CENT = 0.005   # tolerancia de cuadre (medio céntimo)


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _norm(lineas):
    """Normaliza líneas → [{codigo_cuenta, descripcion, debe, haber, tercero, tipo_iva}]."""
    out = []
    for ln in lineas or []:
        cod = ln.get("codigo_cuenta") or ln.get("cuenta") or ln.get("codigo")
        debe = round(float(ln.get("debe") or 0), 2)
        haber = round(float(ln.get("haber") or 0), 2)
        if not cod or (debe == 0 and haber == 0):
            continue
        out.append({"codigo_cuenta": str(cod), "descripcion": ln.get("descripcion"),
                    "debe": debe, "haber": haber, "tercero": ln.get("tercero"),
                    "tipo_iva": ln.get("tipo_iva")})
    return out


def _hash(numero, fecha, total, prev):
    base = f"{numero}|{fecha}|{round(float(total), 2)}|{prev or ''}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def crear_asiento(fecha, lineas, concepto=None, tipo="normal", origen="manual",
                  ref_origen=None, contabilizar=True, usuario=None, id_empresa=None) -> dict | None:
    """Crea un asiento con sus apuntes. Valida cuadre (Σdebe=Σhaber>0). Si el ejercicio
    está cerrado, rechaza. Devuelve {id, numero, anio, estado, total} o None."""
    id_empresa = _empresa(id_empresa)
    if isinstance(fecha, (_dt.date, _dt.datetime)):
        fecha = fecha.strftime("%Y-%m-%d")
    anio = int(str(fecha)[:4])
    aps = _norm(lineas)
    if not aps:
        logger.warning("crear_asiento: sin líneas válidas"); return None
    td = round(sum(a["debe"] for a in aps), 2)
    th = round(sum(a["haber"] for a in aps), 2)
    if td <= 0 or abs(td - th) > _CENT:
        logger.warning("crear_asiento: descuadre debe=%s haber=%s", td, th); return None
    if K.ejercicio_cerrado(anio, id_empresa):
        logger.warning("crear_asiento: ejercicio %s cerrado", anio); return None
    K.crear_ejercicio(anio, id_empresa)            # asegura ejercicio abierto
    ej = K.obtener_ejercicio(anio, id_empresa) or {}
    estado = "contabilizado" if contabilizar else "borrador"
    try:
        with transaccion() as conn, conn.cursor() as cur:
            # Numeración: sobre TODOS los asientos del ejercicio (con bloqueo).
            cur.execute("SELECT COALESCE(MAX(numero),0) FROM contab_asientos WHERE id_empresa=%s "
                        "AND anio=%s FOR UPDATE", (id_empresa, anio))
            r = cur.fetchone()
            numero = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) + 1
            # Hash encadenado: solo sobre los NO-borrador.
            prev_hash = None
            if contabilizar:
                cur.execute("SELECT hash_audit FROM contab_asientos WHERE id_empresa=%s AND anio=%s "
                            "AND estado<>'borrador' ORDER BY numero DESC LIMIT 1", (id_empresa, anio))
                rp = cur.fetchone()
                prev_hash = (rp[0] if rp and not isinstance(rp, dict) else rp.get("hash_audit") if rp else None)
            h = _hash(numero, fecha, td, prev_hash) if contabilizar else None
            cur.execute(
                "INSERT INTO contab_asientos (id_empresa, id_ejercicio, anio, numero, fecha, "
                "concepto, tipo, origen, ref_origen, estado, total_debe, total_haber, hash_audit, "
                "usuario) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, ej.get("id"), anio, numero, fecha, concepto, tipo, origen,
                 ref_origen, estado, td, th, h, usuario))
            aid = cur.lastrowid
            for a in aps:
                cur.execute(
                    "INSERT INTO contab_apuntes (id_asiento, id_empresa, codigo_cuenta, "
                    "descripcion, debe, haber, tercero, tipo_iva) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (aid, id_empresa, a["codigo_cuenta"], a["descripcion"], a["debe"],
                     a["haber"], a["tercero"], a["tipo_iva"]))
        return {"id": aid, "numero": numero, "anio": anio, "estado": estado, "total": td}
    except Exception as e:
        logger.error("crear_asiento: %s", e)
        return None


def obtener_asiento(id_asiento, id_empresa=None) -> dict | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM contab_asientos WHERE id=%s AND id_empresa=%s",
                        (id_asiento, id_empresa))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute("SELECT * FROM contab_apuntes WHERE id_asiento=%s ORDER BY id", (id_asiento,))
            cab["apuntes"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.error("obtener_asiento(%s): %s", id_asiento, e)
        return None


def listar_diario(id_empresa=None, anio=None, desde=None, hasta=None, limite=2000) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s", "estado<>'borrador'"], [id_empresa]
    if anio:
        filtros.append("anio=%s"); params.append(int(anio))
    if desde:
        filtros.append("fecha>=%s"); params.append(desde)
    if hasta:
        filtros.append("fecha<=%s"); params.append(hasta)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM contab_asientos WHERE " + " AND ".join(filtros)
                        + " ORDER BY anio, numero LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_diario: %s", e)
        return []


def contabilizar(id_asiento, id_empresa=None) -> bool:
    """Pasa un borrador a contabilizado (asigna hash de auditoría)."""
    id_empresa = _empresa(id_empresa)
    a = obtener_asiento(id_asiento, id_empresa)
    if not a or a["estado"] != "borrador":
        return False
    if K.ejercicio_cerrado(a["anio"], id_empresa):
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT hash_audit FROM contab_asientos WHERE id_empresa=%s AND anio=%s "
                        "AND estado<>'borrador' AND numero<%s ORDER BY numero DESC LIMIT 1",
                        (id_empresa, a["anio"], a["numero"]))
            r = cur.fetchone()
            prev = (r[0] if r and not isinstance(r, dict) else r.get("hash_audit") if r else None)
            h = _hash(a["numero"], a["fecha"], a["total_debe"], prev)
            cur.execute("UPDATE contab_asientos SET estado='contabilizado', hash_audit=%s "
                        "WHERE id=%s AND id_empresa=%s", (h, id_asiento, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("contabilizar(%s): %s", id_asiento, e)
        return False


def anular(id_asiento, fecha=None, usuario=None, id_empresa=None) -> dict | None:
    """Anula un asiento CONTABILIZADO mediante CONTRAASIENTO (apuntes invertidos).
    No modifica el original (inmutable); lo marca 'anulado' y enlaza el contraasiento."""
    id_empresa = _empresa(id_empresa)
    a = obtener_asiento(id_asiento, id_empresa)
    if not a or a["estado"] != "contabilizado":
        return None
    if K.ejercicio_cerrado(a["anio"], id_empresa):
        logger.warning("anular: ejercicio %s cerrado", a["anio"]); return None
    fecha = fecha or _dt.date.today().strftime("%Y-%m-%d")
    inv = [{"codigo_cuenta": ap["codigo_cuenta"],
            "descripcion": f"Anulación asiento {a['numero']}",
            "debe": float(ap["haber"] or 0), "haber": float(ap["debe"] or 0),
            "tercero": ap.get("tercero"), "tipo_iva": ap.get("tipo_iva")}
           for ap in a["apuntes"]]
    contra = crear_asiento(fecha, inv, concepto=f"Contraasiento del nº {a['numero']}",
                           tipo="contraasiento", origen="anulacion",
                           ref_origen=f"asiento:{id_asiento}", usuario=usuario, id_empresa=id_empresa)
    if not contra:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE contab_asientos SET estado='anulado', anulado_por=%s "
                        "WHERE id=%s AND id_empresa=%s", (contra["id"], id_asiento, id_empresa))
            conn.commit()
    except Exception as e:
        logger.error("anular(%s): %s", id_asiento, e)
    return contra


def cadena_auditoria_valida(id_empresa=None, anio=None) -> bool:
    """Re-deriva el hash encadenado del diario y verifica integridad."""
    id_empresa = _empresa(id_empresa)
    prev = None
    for a in listar_diario(id_empresa, anio=anio, limite=100000):
        if a["estado"] == "anulado":
            # el anulado mantiene su hash original calculado al contabilizar
            esperado = _hash(a["numero"], str(a["fecha"]), a["total_debe"], prev)
        else:
            esperado = _hash(a["numero"], str(a["fecha"]), a["total_debe"], prev)
        if a.get("hash_audit") and a["hash_audit"] != esperado:
            return False
        prev = a.get("hash_audit") or prev
    return True
