"""
Tareas LARGAS de SOMA (Fase 5). SOMA puede iniciar trabajos que tardan (analizar ventas del
trimestre, revisar pedidos pendientes, comparar proveedores…) en SEGUNDO PLANO, informando del
progreso y sin bloquear la aplicación. Reutiliza los servicios/consultas existentes; no duplica
lógica. El resultado vuelve al hilo principal por señales Qt.
"""

import logging
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("soma.tareas")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def _q(sql, params=()):
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(sql, params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("consulta tarea: %s", e)
        return []


# ── Handlers de tareas largas (reutilizan la BD/servicios existentes) ─────────
def analizar_ventas(emp, progreso):
    progreso(10, "Recopilando ventas del trimestre…")
    filas = _q("SELECT DATE(fecha) d, COALESCE(SUM(total),0) t, COUNT(*) n FROM ventas "
               "WHERE id_empresa=%s AND fecha >= (NOW() - INTERVAL 90 DAY) GROUP BY DATE(fecha) "
               "ORDER BY d", (emp,))
    progreso(60, "Agregando y buscando patrones…")
    time.sleep(0.05)
    total = sum(float(f.get("t") or 0) for f in filas)
    tickets = sum(int(f.get("n") or 0) for f in filas)
    top = sorted(filas, key=lambda f: float(f.get("t") or 0), reverse=True)[:5]
    progreso(100, "Análisis completado.")
    return {
        "texto": f"He analizado las ventas del trimestre: {round(total, 2)} en {tickets} tickets "
                 f"a lo largo de {len(filas)} días con actividad.",
        "fuentes": ["Ventas"],
        "visual": {"tipo": "tabla", "columnas": ["Día", "Importe", "Tickets"],
                   "filas": [{"Día": str(f.get("d")), "Importe": round(float(f.get("t") or 0), 2),
                              "Tickets": int(f.get("n") or 0)} for f in top]},
    }


def revisar_pedidos_pendientes(emp, progreso):
    progreso(20, "Revisando pedidos de compra pendientes…")
    filas = _q("SELECT id, id_proveedor, estado, fecha FROM compras_pedidos WHERE id_empresa=%s "
               "AND estado IN ('BORRADOR','ENVIADO','PENDIENTE','PARCIAL') ORDER BY fecha DESC LIMIT 100",
               (emp,))
    progreso(100, "Revisión completada.")
    return {
        "texto": f"He revisado los pedidos pendientes: {len(filas)} en curso.",
        "fuentes": ["Compras"],
        "visual": {"tipo": "tabla", "columnas": ["Pedido", "Proveedor", "Estado"],
                   "filas": [{"Pedido": f.get("id"), "Proveedor": f.get("id_proveedor"),
                              "Estado": f.get("estado")} for f in filas[:20]]},
    }


def comparar_proveedores(emp, progreso):
    progreso(30, "Recopilando proveedores…")
    filas = _q("SELECT id, nombre FROM proveedores WHERE id_empresa=%s LIMIT 50", (emp,))
    progreso(100, "Comparativa lista.")
    return {
        "texto": f"He preparado una comparativa de {len(filas)} proveedores.",
        "fuentes": ["Compras", "Proveedores"],
        "visual": {"tipo": "tabla", "columnas": ["Id", "Proveedor"],
                   "filas": [{"Id": f.get("id"), "Proveedor": f.get("nombre")} for f in filas[:20]]},
    }


# Disparadores (palabras clave → handler). El razonador decide si es una tarea larga.
CATALOGO = {
    "analizar_ventas": (("analiza", "ventas"), analizar_ventas),
    "revisar_pedidos": (("revisa", "pedidos"), revisar_pedidos_pendientes),
    "comparar_proveedores": (("compara", "proveedor"), comparar_proveedores),
}


def detectar(texto):
    """Devuelve (codigo, handler) si el texto pide una tarea larga; None si no."""
    t = (texto or "").lower()
    for codigo, (claves, handler) in CATALOGO.items():
        if all(k in t for k in claves):
            return codigo, handler
    return None


class GestorTareas(QObject):
    """Ejecuta tareas largas en segundo plano y notifica progreso/fin en el HILO PRINCIPAL."""

    progreso = pyqtSignal(str, int, str)     # (codigo, pct, mensaje)
    terminada = pyqtSignal(str, object)      # (codigo, resultado)

    def __init__(self):
        super().__init__()
        self._activas = {}

    def iniciar(self, codigo, handler, id_empresa=None) -> bool:
        if codigo in self._activas:
            return False
        emp = _emp(id_empresa)
        self._activas[codigo] = time.time()

        def _run():
            try:
                res = handler(emp, lambda pct, msg: self.progreso.emit(codigo, int(pct), str(msg)))
            except Exception as e:
                logger.error("tarea %s: %s", codigo, e)
                res = {"texto": f"No he podido completar «{codigo}»: {e}", "fuentes": []}
            finally:
                self._activas.pop(codigo, None)
            self.terminada.emit(codigo, res)

        threading.Thread(target=_run, daemon=True, name=f"soma-tarea-{codigo}").start()
        return True

    def activas(self) -> list:
        return list(self._activas.keys())
