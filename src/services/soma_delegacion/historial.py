"""Historial de evaluaciones/ejecuciones de delegación (`soma_delegaciones_historial`)."""

import json
import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("soma_delegacion.historial")


def _emp(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def registrar(id_regla, tipo, *, contexto=None, decision=None, estado="aplicado",
             resultado=None, id_empresa=None) -> int | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO soma_delegaciones_historial (id_empresa, id_regla, tipo, "
                "contexto_json, decision_json, estado, resultado) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (_emp(id_empresa), id_regla, tipo,
                 json.dumps(contexto) if contexto is not None else None,
                 json.dumps(decision) if decision is not None else None,
                 estado, (resultado or "")[:500]))
            return cur.lastrowid
    except Exception as e:
        logger.error("registrar historial: %s", e)
        return None


def _fila_a_dict(fila):
    fila = dict(fila)
    for campo in ("contexto_json", "decision_json"):
        clave = campo.replace("_json", "")
        try:
            fila[clave] = json.loads(fila.get(campo) or "null")
        except Exception:
            fila[clave] = None
        fila.pop(campo, None)
    return fila


def listar(id_empresa=None, *, id_regla=None, tipo=None, limite=200) -> list:
    filtros, params = ["id_empresa=%s"], [_emp(id_empresa)]
    if id_regla is not None:
        filtros.append("id_regla=%s"); params.append(id_regla)
    if tipo:
        filtros.append("tipo=%s"); params.append(tipo)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM soma_delegaciones_historial WHERE " + " AND ".join(filtros) +
                        " ORDER BY creado DESC LIMIT %s", (*params, int(limite)))
            return [_fila_a_dict(f) for f in _filas_a_dicts(cur, cur.fetchall())]
    except Exception as e:
        logger.error("listar historial: %s", e)
        return []


def actualizar_estado(id_historial, estado, *, resultado=None, id_empresa=None) -> bool:
    """Cambia el estado de una entrada (p. ej. `pendiente_revision` -> `aplicado`/`descartado`
    tras una decisión manual del SUPERADMIN desde la pantalla de Delegación IA)."""
    sets, params = ["estado=%s"], [estado]
    if resultado is not None:
        sets.append("resultado=%s"); params.append(resultado[:500])
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE soma_delegaciones_historial SET {', '.join(sets)} "
                       "WHERE id=%s AND id_empresa=%s", (*params, id_historial, _emp(id_empresa)))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("actualizar_estado historial: %s", e)
        return False


def obtener(id_historial, id_empresa=None) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM soma_delegaciones_historial WHERE id=%s AND id_empresa=%s",
                        (id_historial, _emp(id_empresa)))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return _fila_a_dict(filas[0]) if filas else None
    except Exception as e:
        logger.error("obtener historial: %s", e)
        return None
