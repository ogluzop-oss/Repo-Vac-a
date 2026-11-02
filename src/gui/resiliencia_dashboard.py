"""
GUI Resiliencia (BLOQUE 7): ResilienciaDashboardWindow — estado online/offline, colas, conflictos,
circuit breakers, RPO/RTO, edge nodes. Permite sincronizar, ejecutar watchdog y lanzar chaos.
Reutiliza el estilo global. Aditivo.
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _btn_cargando, _info, _tabla

logger = logging.getLogger("gui.resiliencia")


def _it(v):
    from PyQt6.QtWidgets import QTableWidgetItem
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class ResilienciaDashboardWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Resiliencia · Continuidad operativa")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Watchdog", self._watchdog, primary=True))
        cab.addWidget(_btn("Sincronizar", self._sync, primary=True))
        cab.addWidget(_btn_cargando("🔄  Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tbl_estado = _tabla(["Indicador", "Valor"])
        self.tbl_breakers = _tabla(["Servicio", "Estado", "Fallos"])
        self.tbl_edge = _tabla(["Tienda", "Modo", "Pendientes", "Salud"])
        self.tabs.addTab(self._envolver(self.tbl_estado), "Estado")
        self.tabs.addTab(self._wrap(self.tbl_breakers, self._barra_breakers(), arriba=False), "Cortacircuitos")
        self.tabs.addTab(self._wrap(self.tbl_edge, self._barra_edge(), arriba=True), "Nodos de borde")
        root.addWidget(self.tabs)
        self._load()

    def _envolver(self, tabla):
        """Tabla sin barra de acciones propia: solo el margen superior — pegada directamente al
        borde de la pestaña, su contorno se veía más fino por arriba que por los otros lados."""
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 12, 0, 0)
        lay.addWidget(tabla, 1)
        return w

    def _wrap(self, tabla, barra, *, arriba):
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 12, 0, 0)
        if arriba:
            lay.addLayout(barra)
            lay.addWidget(tabla, 1)
        else:
            lay.addWidget(tabla, 1)
            lay.addLayout(barra)
        return w

    def _barra_breakers(self):
        b = QHBoxLayout(); b.addStretch(1)
        b.addWidget(_btn("Resetear breaker", self._resetear_breaker, primary=True))
        return b

    def _barra_edge(self):
        b = QHBoxLayout(); b.addStretch(1)
        b.addWidget(_btn("Forzar reconexión", self._reconectar_nodo, primary=True))
        b.addWidget(_btn("Forzar offline", self._forzar_offline_nodo, primary=True))
        return b

    def _resetear_breaker(self):
        r = self.tbl_breakers.currentRow()
        if r < 0 or self.tbl_breakers.item(r, 0) is None:
            _info(self, "Cortacircuitos", "Selecciona antes un servicio en la tabla.")
            return
        servicio = self.tbl_breakers.item(r, 0).text()
        from src.services.resiliencia import circuit_breaker
        if circuit_breaker.resetear(servicio, id_empresa=_empresa()):
            _info(self, "Cortacircuitos", f"Breaker de «{servicio}» reseteado (cerrado, fallos a 0).")
            self._load()
        else:
            _info(self, "Cortacircuitos", "No se pudo resetear el breaker.")

    def _edge_tienda_sel(self):
        r = self.tbl_edge.currentRow()
        if r < 0 or self.tbl_edge.item(r, 0) is None:
            _info(self, "Nodos de borde", "Selecciona antes una tienda en la tabla.")
            return None
        try:
            return int(self.tbl_edge.item(r, 0).text())
        except (TypeError, ValueError):
            return None

    def _reconectar_nodo(self):
        id_tienda = self._edge_tienda_sel()
        if id_tienda is None:
            return
        from src.services.resiliencia import edge_node
        r = edge_node.reconectar(_empresa(), id_tienda)
        _info(self, "Nodos de borde", f"Tienda {id_tienda} reconectada (modo: {r.get('modo')}).")
        self._load()

    def _forzar_offline_nodo(self):
        id_tienda = self._edge_tienda_sel()
        if id_tienda is None:
            return
        from src.services.resiliencia import edge_node
        r = edge_node.entrar_offline(_empresa(), id_tienda)
        _info(self, "Nodos de borde", f"Tienda {id_tienda} forzada a modo offline (modo: {r.get('modo')}).")
        self._load()

    def _load(self):
        try:
            from src.services.resiliencia import resilience_dashboard
            p = resilience_dashboard.panel(id_empresa=_empresa())
            rr = p.get("rpo_rto", {})
            filas = [
                ("Salud general", p.get("salud")),
                ("Sync pendientes", p.get("sync_pendientes")),
                ("Conflictos", p.get("conflictos")),
                ("Breakers abiertos", ", ".join(p.get("breakers_abiertos", [])) or "0"),
                ("Tiendas offline/degradado", p.get("tiendas_offline")),
                ("RPO backup (h)", rr.get("rpo_backup")),
                ("RTO backup (min)", rr.get("rto_backup")),
                ("Última sincronización", p.get("ultima_sincronizacion")),
            ]
            self.tbl_estado.setRowCount(len(filas))
            for i, (k, v) in enumerate(filas):
                self.tbl_estado.setItem(i, 0, _it(k)); self.tbl_estado.setItem(i, 1, _it(v))
            br = p.get("circuit_breakers", [])
            self.tbl_breakers.setRowCount(len(br))
            for i, b in enumerate(br):
                for j, v in enumerate([b.get("servicio"), b.get("estado"), b.get("fallos")]):
                    self.tbl_breakers.setItem(i, j, _it(v))
            edge = p.get("edge_nodes", [])
            self.tbl_edge.setRowCount(len(edge))
            for i, n in enumerate(edge):
                for j, v in enumerate([n.get("id_tienda"), n.get("modo"), n.get("eventos_pendientes"),
                                       n.get("salud")]):
                    self.tbl_edge.setItem(i, j, _it(v))
            self.lbl.setText(f"Salud: {p.get('salud')} · Sync pendientes: {p.get('sync_pendientes')}")
        except Exception as e:
            logger.error("load resiliencia: %s", e)
            self.lbl.setText(f"Error: {e}")

    def _sync(self):
        try:
            from src.services.resiliencia import sync_engine
            r = sync_engine.push_offline_a_central(id_empresa=_empresa())
            _info(self, "Sync", f"Sincronizado: {r['resumen']}")
            self._load()
        except Exception as e:
            _info(self, "Sync", f"Error: {e}")

    def _watchdog(self):
        try:
            from src.services.resiliencia import resilience_watchdog
            r = resilience_watchdog.ejecutar(id_empresa=_empresa())
            acciones = r.get("acciones") or []
            texto = ("Sin acciones necesarias: no se han detectado incidencias."
                     if not acciones else "Acciones aplicadas:\n· " + "\n· ".join(acciones))
            _info(self, "Watchdog", texto)
            self._load()
        except Exception as e:
            _info(self, "Watchdog", f"Error: {e}")
