"""
Historial de simulaciones de la Calculadora Fiscal (Contabilidad) — cada `simular()` con éxito se
guarda automáticamente (sin paso manual de "guardar", para no perder ninguna simulación). Mismas
formas que `services.simulador.motor.SimulationService` (crear/listar/eliminar), simplificado a un
único registro por simulación sobre `fiscal_is_simulaciones` (migr. 0239).
"""

import json
import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("contab.calculadora_fiscal_historial")


def _empresa(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def guardar(entrada: dict, resultado: dict, *, usuario=None, id_empresa=None) -> int | None:
    entrada = entrada or {}
    resultado = resultado or {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO fiscal_is_simulaciones (id_empresa, usuario, anio, tipo_entidad, ccaa, "
                "entrada_json, resultado_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (_empresa(id_empresa), usuario, entrada.get("anio"), entrada.get("tipo_entidad"),
                 entrada.get("ccaa"), json.dumps(entrada, ensure_ascii=False, default=str),
                 json.dumps(resultado, ensure_ascii=False, default=str)))
            return cur.lastrowid
    except Exception as e:
        logger.error("guardar: %s", e)
        return None


def listar(id_empresa=None, limite=50) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, usuario, anio, tipo_entidad, ccaa, resultado_json, creado "
                "FROM fiscal_is_simulaciones WHERE id_empresa=%s ORDER BY creado DESC LIMIT %s",
                (_empresa(id_empresa), int(limite)))
            filas = _filas_a_dicts(cur, cur.fetchall())
        for f in filas:
            try:
                f["resultado"] = json.loads(f.pop("resultado_json") or "{}")
            except Exception:
                f["resultado"] = {}
        return filas
    except Exception as e:
        logger.error("listar: %s", e)
        return []


def obtener(id_sim, id_empresa=None) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_is_simulaciones WHERE id=%s AND id_empresa=%s",
                        (id_sim, _empresa(id_empresa)))
            filas = _filas_a_dicts(cur, cur.fetchall())
        if not filas:
            return None
        r = filas[0]
        try:
            r["entrada"] = json.loads(r.pop("entrada_json") or "{}")
        except Exception:
            r["entrada"] = {}
        try:
            r["resultado"] = json.loads(r.pop("resultado_json") or "{}")
        except Exception:
            r["resultado"] = {}
        return r
    except Exception as e:
        logger.error("obtener(%s): %s", id_sim, e)
        return None


def eliminar(id_sim, id_empresa=None) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM fiscal_is_simulaciones WHERE id=%s AND id_empresa=%s",
                        (id_sim, _empresa(id_empresa)))
            return True
    except Exception as e:
        logger.error("eliminar(%s): %s", id_sim, e)
        return False
