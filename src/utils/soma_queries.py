"""
SOMA Queries — Real-time DB queries for the SOMA voice assistant.
All functions return a human-readable Spanish string ready to be spoken via TTS.
Errors are handled silently and return a friendly fallback message.
"""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger("soma.queries")


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


# ─── Stock ────────────────────────────────────────────────────────────────────

def stock_articulo(termino: str) -> str:
    """
    Returns spoken stock info for the article matching `termino`
    (searches by code first, then by name with LIKE).
    """
    if not termino or len(termino) < 2:
        return "No he entendido el artículo que quieres consultar. Inténtalo de nuevo."
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                # 1st: exact code match
                cur.execute(
                    "SELECT descripcion, Stock_tienda, Stock_almacen "
                    "FROM articulos WHERE UPPER(codigo) = %s LIMIT 1",
                    (termino.upper(),)
                )
                row = cur.fetchone()

                # 2nd: partial name match
                if not row:
                    cur.execute(
                        "SELECT descripcion, Stock_tienda, Stock_almacen "
                        "FROM articulos WHERE descripcion LIKE %s LIMIT 1",
                        (f"%{termino}%",)
                    )
                    row = cur.fetchone()

                if not row:
                    return f"No he encontrado ningún artículo llamado {termino}."

                nombre, stock_t, stock_a = row
                stock_t = int(stock_t or 0)
                stock_a = int(stock_a or 0)

                if stock_t == 0 and stock_a == 0:
                    return f"{nombre} no tiene stock disponible en este momento."
                partes = [f"{nombre} tiene {stock_t} unidades en tienda"]
                if stock_a:
                    partes.append(f"y {stock_a} en almacén")
                return ". ".join(partes) + "."

    except Exception as e:
        logger.error(f"soma_queries.stock_articulo: {e}")
        return "No he podido consultar el stock. Comprueba la conexión a la base de datos."


def articulos_criticos() -> str:
    """Returns list of articles with critically low stock."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT descripcion, Stock_tienda "
                    "FROM articulos "
                    "WHERE Stock_tienda IS NOT NULL AND Stock_tienda < 5 "
                    "ORDER BY Stock_tienda ASC LIMIT 6"
                )
                rows = cur.fetchall()

        if not rows:
            return "No hay artículos en stock crítico en este momento. Buen trabajo."

        total = len(rows)
        nombres = [f"{r[0]} con {int(r[1] or 0)} unidades" for r in rows[:3]]
        respuesta = f"Hay {total} artículo{'s' if total > 1 else ''} con stock crítico: "
        respuesta += ", ".join(nombres)
        if total > 3:
            respuesta += f" y {total - 3} más."
        return respuesta

    except Exception as e:
        logger.error(f"soma_queries.articulos_criticos: {e}")
        return "No he podido consultar el stock crítico."


# ─── Ventas ───────────────────────────────────────────────────────────────────

def ventas_hoy() -> str:
    """Returns today's sales summary."""
    try:
        hoy = date.today().isoformat()
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*), SUM(cantidad), SUM(total) "
                    "FROM ventas WHERE DATE(fecha) = %s",
                    (hoy,)
                )
                row = cur.fetchone()

        if not row or not row[0]:
            return "Todavía no hay ventas registradas hoy."

        n_ventas, uds, total = row
        uds   = int(uds or 0)
        total = float(total or 0)
        return (
            f"Hoy se han registrado {n_ventas} venta{'s' if n_ventas != 1 else ''}, "
            f"{uds} unidades vendidas "
            f"por un total de {total:.2f} euros."
        )

    except Exception as e:
        logger.error(f"soma_queries.ventas_hoy: {e}")
        return "No he podido consultar las ventas de hoy."


# ─── Traspasos ────────────────────────────────────────────────────────────────

def traspasos_pendientes() -> str:
    """Returns count and destinations of pending transfers."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*), destino "
                    "FROM documentos_logisticos "
                    "WHERE estado IN ('EN_TRANSITO','EN TRÁNSITO','PREPARADO','EN_PREPARACION') "
                    "GROUP BY destino ORDER BY COUNT(*) DESC"
                )
                rows = cur.fetchall()

        if not rows:
            return "No hay traspasos pendientes en este momento."

        total = sum(r[0] for r in rows)
        destinos = [f"{r[1]} ({r[0]})" for r in rows[:2]]
        texto = f"Hay {total} traspaso{'s' if total != 1 else ''} pendiente{'s' if total != 1 else ''}"
        texto += f", hacia {', '.join(destinos)}"
        if len(rows) > 2:
            texto += f" y {len(rows) - 2} destino{'s' if len(rows) - 2 > 1 else ''} más"
        return texto + "."

    except Exception as e:
        logger.error(f"soma_queries.traspasos_pendientes: {e}")
        return "No he podido consultar los traspasos pendientes."


# ─── Mermas ───────────────────────────────────────────────────────────────────

def mermas_mes() -> str:
    """Returns mermas count and quantity for the current month."""
    try:
        mes = date.today().strftime("%Y-%m")
        with _conn() as conn:
            with conn.cursor() as cur:
                # Try different column names gracefully
                try:
                    cur.execute(
                        "SELECT COUNT(*), SUM(cantidad) FROM mermas "
                        "WHERE DATE_FORMAT(fecha, '%Y-%m') = %s",
                        (mes,)
                    )
                except Exception:
                    cur.execute("SELECT COUNT(*), NULL FROM mermas LIMIT 1")
                row = cur.fetchone()

        if not row or not row[0]:
            return "No hay mermas registradas este mes."

        n = int(row[0])
        qty = int(row[1] or 0) if row[1] else None
        texto = f"Este mes se han registrado {n} merma{'s' if n != 1 else ''}"
        if qty:
            texto += f" con un total de {qty} unidades afectadas"
        return texto + "."

    except Exception as e:
        logger.error(f"soma_queries.mermas_mes: {e}")
        return "No he podido consultar las mermas de este mes."


# ─── Usuario / Sistema ────────────────────────────────────────────────────────

def info_usuario_actual() -> str:
    """Returns current logged-in user info."""
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual
        if not u:
            return "No hay ningún usuario conectado en este momento."
        nombre = u.get("nombre", "Usuario desconocido")
        perfil = u.get("perfil", "sin perfil")
        return f"Estás conectado como {nombre}, con perfil de {perfil.lower()}."
    except Exception as e:
        logger.error(f"soma_queries.info_usuario: {e}")
        return "No he podido obtener la información del usuario."


def info_hora_fecha() -> str:
    """Returns current time and date."""
    from datetime import datetime
    ahora = datetime.now()
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    dia_semana = dias[ahora.weekday()]
    mes = meses[ahora.month - 1]
    return (
        f"Son las {ahora.strftime('%H:%M')} horas. "
        f"Hoy es {dia_semana}, {ahora.day} de {mes} de {ahora.year}."
    )
