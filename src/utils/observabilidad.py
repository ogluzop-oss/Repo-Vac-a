"""
Observabilidad mínima operativa (E1.6) — diagnóstico básico en producción.

No es APM: es la capacidad de RESPONDER en soporte a "¿qué pasa?" con datos reales:
- `registrar_evento(...)`: log unificado de eventos clave (arranque, login, backup,
  restauración, fiscal) bajo el logger `smart_manager.eventos`.
- `estado_sistema()`: foto de salud (BD, migraciones, fiscal, backups, logs).
- `diagnostico_texto()`: informe legible para soporte.

El logging global (fichero rotativo + captura de excepciones no controladas de
hilo/threads/Qt) ya lo provee `utils.logger`; aquí se añade el diagnóstico.
"""

import logging
import os

_EVENTOS = logging.getLogger("smart_manager.eventos")
_NIVEL = {"info": logging.INFO, "warning": logging.WARNING,
          "error": logging.ERROR, "critical": logging.CRITICAL}


def registrar_evento(categoria: str, mensaje: str, nivel: str = "info", **datos):
    """Registra un evento operativo. `categoria` ∈ arranque|login|backup|restore|
    fiscal|… . Los `datos` se añaden como contexto (sin secretos)."""
    extra = (" | " + " ".join(f"{k}={v}" for k, v in datos.items())) if datos else ""
    _EVENTOS.log(_NIVEL.get(nivel, logging.INFO), "[%s] %s%s", categoria, mensaje, extra)


def _db_ok() -> bool:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception:
        return False


def _migracion_actual():
    try:
        from src.db import migrador
        aplicadas = [m for m in migrador.estado() if m.get("aplicada")]
        return aplicadas[-1]["version"] if aplicadas else None
    except Exception:
        return None


def _fiscal_estado() -> dict:
    try:
        from src.db import fiscal as F
        c = F.obtener_config()
        return {"activo": bool(c.get("activo")), "proveedor": c.get("proveedor"),
                "modo": c.get("modo"), "entorno": c.get("entorno")}
    except Exception:
        return {}


def _backups_estado() -> dict:
    try:
        from src.db import backup as B
        lista = B.listar_backups()
        return {"total": len(lista), "ultimo": (lista[0].get("fecha") if lista else None)}
    except Exception:
        return {"total": 0, "ultimo": None}


def _log_info() -> dict:
    try:
        from src.utils.logger import _dir_logs
        d = _dir_logs()
        fichero = os.path.join(d, "smart_manager.log")
        errores = 0
        if os.path.exists(fichero):
            with open(fichero, encoding="utf-8", errors="ignore") as fh:
                cola = fh.readlines()[-500:]
            errores = sum(1 for ln in cola if "| CRITICAL" in ln or "| ERROR" in ln)
        return {"dir": d, "fichero": fichero, "errores_recientes": errores}
    except Exception:
        return {"dir": None, "fichero": None, "errores_recientes": 0}


def estado_sistema() -> dict:
    """Foto de salud del sistema para diagnóstico operativo."""
    return {
        "db_ok": _db_ok(),
        "migracion_actual": _migracion_actual(),
        "fiscal": _fiscal_estado(),
        "backups": _backups_estado(),
        "logs": _log_info(),
    }


def diagnostico_texto() -> str:
    """Informe de diagnóstico legible (para soporte)."""
    e = estado_sistema()
    f, b, lg = e["fiscal"], e["backups"], e["logs"]
    return (
        "=== Diagnóstico Smart Manager AI ===\n"
        f"Base de datos:   {'OK' if e['db_ok'] else 'SIN CONEXIÓN'}\n"
        f"Migración:       {e['migracion_actual'] or 'desconocida'}\n"
        f"Fiscal:          activo={f.get('activo')} proveedor={f.get('proveedor')} "
        f"modo={f.get('modo')} entorno={f.get('entorno')}\n"
        f"Backups:         {b.get('total')} (último: {b.get('ultimo')})\n"
        f"Logs:            {lg.get('fichero')} (errores recientes: {lg.get('errores_recientes')})\n"
    )
