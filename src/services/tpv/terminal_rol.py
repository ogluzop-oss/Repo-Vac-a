"""
Rol del TERMINAL — resuelve qué interfaz debe arrancar esta máquina (cajero vs. autocobro).

La interfaz NO la decide el usuario con un botón, sino el ENTORNO donde se ejecuta el software:

  1. Variable de entorno / `.env`  →  `TERMINAL_ROL` (o `TERMINAL_TYPE`):
        TPV | CAJERO | TRADICIONAL          → rol TPV (interfaz de cajero, ERP completo)
        AUTOCOBRO | SELF_CHECKOUT | KIOSCO  → rol AUTOCOBRO (kiosco de cliente)
  2. Si no hay variable pero sí `TERMINAL_CODIGO`  →  se consulta `ioc_terminales.tipo_dispositivo`
     (identidad operativa ya existente, migr 0121) por `codigo_terminal`.
  3. Por defecto  →  TPV (comportamiento actual; no rompe instalaciones existentes).

Servicio API-First (sin PyQt), degradable: si la BD no está disponible cae al valor por defecto.
Reutiliza `ioc_terminales`; no crea motores ni tablas nuevas.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("tpv.terminal_rol")

ROL_TPV = "TPV"
ROL_AUTOCOBRO = "AUTOCOBRO"

# Sinónimos aceptados en la configuración (tolerante a mayúsculas/idioma).
_ALIAS = {
    "TPV": ROL_TPV, "CAJERO": ROL_TPV, "CAJA": ROL_TPV, "TRADICIONAL": ROL_TPV,
    "TRADITIONAL": ROL_TPV, "ERP": ROL_TPV,
    "AUTOCOBRO": ROL_AUTOCOBRO, "SELF_CHECKOUT": ROL_AUTOCOBRO, "SELFCHECKOUT": ROL_AUTOCOBRO,
    "SELF-CHECKOUT": ROL_AUTOCOBRO, "KIOSCO": ROL_AUTOCOBRO, "KIOSK": ROL_AUTOCOBRO,
    "TOTEM": ROL_AUTOCOBRO, "TÓTEM": ROL_AUTOCOBRO,
}


def _normaliza(valor: str | None) -> str | None:
    if not valor:
        return None
    return _ALIAS.get(valor.strip().upper())


def _rol_por_codigo(codigo: str) -> str | None:
    """Consulta `ioc_terminales.tipo_dispositivo` por código de terminal. Degradable (None si falla)."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT tipo_dispositivo FROM ioc_terminales "
                "WHERE codigo_terminal=%s AND activo=1 ORDER BY fecha_alta DESC LIMIT 1",
                (codigo,))
            row = cur.fetchone()
            if row:
                return _normaliza(row[0])
    except Exception as e:
        logger.debug(f"_rol_por_codigo degradado: {e}")
    return None


def rol_terminal() -> str:
    """Devuelve el rol de ESTE terminal: ROL_TPV o ROL_AUTOCOBRO. Nunca lanza (por defecto TPV)."""
    # 1) Variable de entorno explícita.
    env = _normaliza(os.getenv("TERMINAL_ROL") or os.getenv("TERMINAL_TYPE"))
    if env:
        return env
    # 2) Código de terminal → identidad operativa (ioc_terminales).
    codigo = (os.getenv("TERMINAL_CODIGO") or "").strip()
    if codigo:
        por_codigo = _rol_por_codigo(codigo)
        if por_codigo:
            return por_codigo
    # 3) Por defecto: cajero (comportamiento actual).
    return ROL_TPV


def es_autocobro() -> bool:
    return rol_terminal() == ROL_AUTOCOBRO


def id_caja(defecto: str = "AUTO-01") -> str:
    """ID de caja/terminal para el autocobro (permite AUTO-01, AUTO-02…). Env `TERMINAL_CAJA`."""
    return (os.getenv("TERMINAL_CAJA") or os.getenv("TERMINAL_CODIGO") or defecto).strip() or defecto


def descriptor() -> dict:
    """Diagnóstico del rol resuelto (para logs / pantallas de estado)."""
    return {
        "rol": rol_terminal(),
        "codigo_terminal": (os.getenv("TERMINAL_CODIGO") or "").strip() or None,
        "id_caja": id_caja(),
        "fuente": ("env" if (os.getenv("TERMINAL_ROL") or os.getenv("TERMINAL_TYPE")) else
                   "ioc_terminales" if (os.getenv("TERMINAL_CODIGO") or "").strip() else "defecto"),
    }
