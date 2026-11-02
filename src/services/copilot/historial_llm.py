"""
Historial de conversacion LLM de SOMA (migr. 0284, `soma_conversaciones_turnos`).

Unico punto de persistencia/lectura del historial turno-a-turno que `motor_llm.py` necesita para
construir `messages=[...]` en cada llamada a `anthropic.messages.create(...)` — a diferencia de
`soma_memoria`/`copilot.memoria` (habitos/resumen, nunca texto de conversacion real), ver la
migracion para el detalle completo.

Tambien es el soporte de la maquina de estados de confirmacion humana: una fila rol='tool' con
`tool_result_json IS NULL` es una propuesta de tool de ESCRITURA pendiente de que el usuario
confirme en su SIGUIENTE turno (ver `obtener_turno_pendiente`/`resolver_turno_pendiente` y
`motor_llm.py`).
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("copilot.historial_llm")

_ROLES_VALIDOS = ("user", "assistant", "tool")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def anadir_turno(usuario, id_empresa, rol: str, contenido: str | None, *,
                  tool_name: str | None = None, tool_args: dict | None = None,
                  tool_result: dict | None = None) -> int:
    """Persiste un turno de la conversacion. `rol` es 'user'/'assistant'/'tool'. Para un turno de
    propuesta de tool pendiente de confirmacion, llamar con `tool_result=None` (marca el estado
    PENDIENTE); para resolverlo despues, usar `resolver_turno_pendiente`. Devuelve el id de la fila
    insertada (0 si falla, best-effort — nunca rompe la conversacion por un fallo de auditoria)."""
    if rol not in _ROLES_VALIDOS:
        raise ValueError(f"rol de turno desconocido: {rol!r}")
    if not usuario:
        return 0
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO soma_conversaciones_turnos "
                "(id_empresa, usuario, rol, contenido, tool_name, tool_args_json, tool_result_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (emp, str(usuario)[:80], rol, contenido,
                 tool_name,
                 json.dumps(tool_args, ensure_ascii=False) if tool_args is not None else None,
                 json.dumps(tool_result, ensure_ascii=False) if tool_result is not None else None),
            )
            conn.commit()
            return int(cur.lastrowid or 0)
    except Exception as e:
        logger.error("anadir_turno: fallo al persistir (usuario=%s empresa=%s rol=%s): %s",
                     usuario, emp, rol, e)
        return 0


def obtener_historial(usuario, id_empresa, limite: int = 20) -> list[dict]:
    """Devuelve los ultimos `limite` turnos user/assistant (el estado de confirmacion de una tool
    pendiente NO se expone aqui — eso lo resuelve `obtener_turno_pendiente`) en orden
    CRONOLOGICO ascendente, listos para `messages=[...]` de `anthropic.messages.create`: cada
    elemento es `{"role": "user"|"assistant", "content": "..."}`."""
    emp = _emp(id_empresa)
    if not usuario:
        return []
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT rol, contenido FROM soma_conversaciones_turnos "
                "WHERE usuario=%s AND (id_empresa=%s OR (%s IS NULL AND id_empresa IS NULL)) "
                "AND rol IN ('user','assistant') "
                "ORDER BY id DESC LIMIT %s",
                (str(usuario)[:80], emp, emp, max(1, int(limite))),
            )
            filas = cur.fetchall() or []
    except Exception as e:
        logger.error("obtener_historial: fallo al leer (usuario=%s empresa=%s): %s", usuario, emp, e)
        return []
    filas = list(reversed(filas))
    return [{"role": f[0], "content": f[1] or ""} for f in filas]


def obtener_turno_pendiente(usuario, id_empresa) -> dict | None:
    """Devuelve el turno rol='tool' MAS RECIENTE con `tool_result_json IS NULL` (una propuesta de
    tool de escritura a la espera de confirmacion humana en el turno siguiente), o None si no hay
    ninguno pendiente. Forma: `{"id", "tool_name", "tool_args"}`."""
    emp = _emp(id_empresa)
    if not usuario:
        return None
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, tool_name, tool_args_json FROM soma_conversaciones_turnos "
                "WHERE usuario=%s AND (id_empresa=%s OR (%s IS NULL AND id_empresa IS NULL)) "
                "AND rol='tool' AND tool_result_json IS NULL "
                "ORDER BY id DESC LIMIT 1",
                (str(usuario)[:80], emp, emp),
            )
            fila = cur.fetchone()
    except Exception as e:
        logger.error("obtener_turno_pendiente: fallo al leer (usuario=%s empresa=%s): %s",
                     usuario, emp, e)
        return None
    if not fila:
        return None
    try:
        args = json.loads(fila[2]) if fila[2] else {}
    except Exception:
        args = {}
    return {"id": int(fila[0]), "tool_name": fila[1], "tool_args": args}


def resolver_turno_pendiente(id_turno: int, tool_result: dict) -> bool:
    """Marca el turno pendiente `id_turno` como RESUELTO, persistiendo su resultado real (o
    `{"cancelado": true}` si el usuario no confirmo). A partir de aqui deja de contar como
    pendiente para `obtener_turno_pendiente`."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE soma_conversaciones_turnos SET tool_result_json=%s "
                "WHERE id=%s AND rol='tool'",
                (json.dumps(tool_result, ensure_ascii=False), id_turno),
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("resolver_turno_pendiente: fallo al actualizar id=%s: %s", id_turno, e)
        return False


__all__ = ["anadir_turno", "obtener_historial", "obtener_turno_pendiente", "resolver_turno_pendiente"]
