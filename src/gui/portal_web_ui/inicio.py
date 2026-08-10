"""
Portal Web · Sección INICIO (dashboard) — Fase WEB-09.

Dashboard del empleado: reutiliza EXACTAMENTE los servicios existentes (no calcula datos nuevos):
ventas del día (`online_orders_service.facturacion_por_dia`), pedidos/reservas pendientes
(`listar_pedidos_online`/`listar_reservas`), stock crítico (`db.reabastecimiento.listar_propuestas`),
avisos e incidencias (`services.notificaciones`). Solo presentación; todo degradable.
"""

from datetime import date

from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QScrollArea,
                             QVBoxLayout, QWidget)

from src.gui._neon_ui import _BG, _BG2, _BORDE, _CIAN, _TEXT, _TEXT2, _VERDE
from src.gui.portal_web_ui.componentes import (KpiCard, PanelSeccion,
                                               perfil_actual, usuario_actual)


def _n(fn, *a, **kw):
    """Ejecuta un proveedor de datos degradable → longitud/valor o 0."""
    try:
        return fn(*a, **kw)
    except Exception:
        return None


class SeccionInicio(PanelSeccion):
    def __init__(self, empleado="—", parent=None):
        super().__init__("Inicio", "🏠", parent)
        self._empleado = empleado
        self.breadcrumb.set_ruta(["Portal Web", "Inicio"])
        self.toolbar.add("🔄  Actualizar", self.refrescar)

        # ── KPIs ──
        self._grid = QGridLayout()
        self._grid.setSpacing(10)
        self.cuerpo.addLayout(self._grid)
        self._kpi_ventas = KpiCard("Ventas del día", "—", "canal online", _VERDE)
        self._kpi_pedidos = KpiCard("Pedidos pendientes", "—", "por preparar", _CIAN)
        self._kpi_reservas = KpiCard("Reservas pendientes", "—", "Click & Collect", _CIAN)
        self._kpi_encargos = KpiCard("Encargos pendientes", "—", "en curso", _CIAN)
        self._kpi_stock = KpiCard("Stock crítico", "—", "bajo mínimos", "#F1C40F")
        self._kpi_clientes = KpiCard("Clientes", "—", "nuevos / total", _CIAN)
        self._kpi_notif = KpiCard("Notificaciones", "—", "pendientes", "#F1C40F")
        # 4 por fila → responsive (escritorio/portátil/tablet).
        for i, k in enumerate((self._kpi_ventas, self._kpi_pedidos, self._kpi_reservas,
                               self._kpi_encargos, self._kpi_stock, self._kpi_clientes,
                               self._kpi_notif)):
            self._grid.addWidget(k, i // 4, i % 4)

        # ── Avisos / incidencias + accesos rápidos ──
        cols = QHBoxLayout()
        cols.setSpacing(12)
        self.cuerpo.addLayout(cols, 1)
        self._avisos_box = self._panel("🔔  Avisos")
        self._incid_box = self._panel("🚩  Últimas incidencias")
        cols.addWidget(self._avisos_box["frame"], 1)
        cols.addWidget(self._incid_box["frame"], 1)

        self.refrescar()

    def _panel(self, titulo):
        from PyQt6.QtWidgets import QFrame
        f = QFrame()
        f.setStyleSheet("QFrame{background:transparent;border:none;}")
        ly = QVBoxLayout(f)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(6)
        # Subtítulo SIN recuadro.
        t = QLabel(titulo)
        t.setStyleSheet(f"color:{_CIAN};font-weight:800;font-size:13px;background:transparent;")
        ly.addWidget(t)
        # Recuadro gris SOLO alrededor del CONTENIDO (la lista), no del subtítulo. ObjectName para que el
        # borde NO cascadee al QScrollArea interno (que también es un QFrame) → evita el doble contorno.
        caja = QFrame()
        caja.setObjectName("panel_caja")
        caja.setStyleSheet(f"QFrame#panel_caja{{background:{_BG2};border:1px solid {_BORDE};"
                           f"border-radius:12px;}}")
        cl = QVBoxLayout(caja)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(6)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.Shape.NoFrame)
        sc.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        cont = QWidget()
        cont.setStyleSheet("background:transparent;")
        lst = QVBoxLayout(cont)
        lst.setContentsMargins(0, 0, 0, 0)
        lst.setSpacing(4)
        sc.setWidget(cont)
        cl.addWidget(sc, 1)
        ly.addWidget(caja, 1)
        return {"frame": f, "lista": lst}

    def _pintar_lista(self, box, items, vacio="Sin registros."):
        lst = box["lista"]
        while lst.count():
            it = lst.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
        if not items:
            lb = QLabel("· " + vacio)
            lb.setStyleSheet(f"color:{_TEXT2};font-size:11px;")
            lst.addWidget(lb)
            return
        for txt in items:
            lb = QLabel("· " + str(txt))
            lb.setWordWrap(True)
            lb.setStyleSheet(f"color:{_TEXT};font-size:11px;")
            lst.addWidget(lb)
        lst.addStretch()

    def refrescar(self):
        # Ventas del día (online).
        try:
            from src.services.tpv import online_orders_service as OS
            hoy = str(date.today())
            fact = OS.facturacion_por_dia(fecha_desde=hoy, fecha_hasta=hoy) or {}
            self._kpi_ventas.set_valor(f"{float(fact.get(hoy, 0)):,.2f} €")
        except Exception:
            self._kpi_ventas.set_valor("—")
        # Pedidos pendientes.
        try:
            from src.services.tpv import online_orders_service as OS
            peds = OS.listar_pedidos_online(estado="PENDIENTE") or []
            self._kpi_pedidos.set_valor(len(peds))
        except Exception:
            self._kpi_pedidos.set_valor("—")
        # Reservas pendientes (todas las reservas activas del canal).
        reservas = _n(_reservas) or []
        self._kpi_reservas.set_valor(len(reservas))
        # Encargos pendientes (reservas de tipo encargo; degradable a 0).
        encargos = _n(_reservas, tipo="ENCARGO") or []
        self._kpi_encargos.set_valor(len(encargos))
        # Stock crítico (propuestas de reabastecimiento pendientes).
        try:
            from src.db import reabastecimiento as R
            props = R.listar_propuestas() or []
            self._kpi_stock.set_valor(len(props))
        except Exception:
            self._kpi_stock.set_valor("—")
        # Clientes (nuevos hoy / total).
        try:
            from datetime import date as _d

            from src.db import clientes as C
            todos = C.listar_clientes(limite=100000) or []
            hoy = str(_d.today())
            nuevos = sum(1 for c in todos
                         if str(c.get("fecha_alta") or c.get("creado") or c.get("fecha") or "")[:10] == hoy)
            self._kpi_clientes.set_valor(nuevos, f"nuevos hoy · {len(todos)} total")
        except Exception:
            self._kpi_clientes.set_valor("—")
        # Notificaciones pendientes.
        try:
            from src.services import notificaciones as N
            u = usuario_actual()
            pend = N.pendientes_usuario(u, perfil=perfil_actual()) if u else N.listar(limite=500)
            self._kpi_notif.set_valor(len(pend or []))
        except Exception:
            self._kpi_notif.set_valor("—")
        # Avisos / incidencias (notificaciones del usuario/empresa).
        self._pintar_lista(self._avisos_box, _n(_avisos) or [], "Sin avisos.")
        self._pintar_lista(self._incid_box, _n(_incidencias) or [], "Sin incidencias.")


# ── Proveedores de datos degradables (reutilizan servicios existentes) ────────
def _reservas(estado=None, tipo=None):
    from src.services.tpv import online_orders_service as OS
    return OS.listar_reservas(estado=estado, tipo=tipo)


def _avisos():
    from src.services import notificaciones as N
    u = usuario_actual()
    filas = N.pendientes_usuario(u, perfil=perfil_actual()) if u else N.listar(limite=20)
    return [f.get("titulo") or f.get("mensaje") or f.get("asunto") or "—" for f in (filas or [])][:15]


def _incidencias():
    from src.services import notificaciones as N
    filas = N.listar(modulo="incidencias", limite=15) or N.listar(prioridad="alta", limite=15) or []
    return [f.get("titulo") or f.get("mensaje") or "—" for f in filas][:15]
