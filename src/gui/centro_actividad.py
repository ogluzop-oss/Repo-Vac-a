"""
Centro de Actividad Empresarial (Fase 3, SUBFASE 3.1/3.7/3.8/3.9).

Evolucion de "Notificaciones": no es una lista de mensajes, es la LINEA DE TIEMPO de toda la
actividad del ERP (alimentada por el Event Bus) + el PANEL DE SINCRONIZACION por terminal.
Doble clic en una actividad → historial completo (quien/cuando/desde donde/aplicado).

Solo presentacion; la logica vive en src.services.actividad (multiempresa + alcance por
usuario). No modifica ningun flujo del ERP.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _btn, _btn_x, _combo, _inp, _tabla)
from src.services import actividad as _ACT

logger = logging.getLogger("gui.centro_actividad")

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

_COL_PRIO = {"CRITICA": "#F85149", "ALTA": "#F0A020", "MEDIA": "#00FFC6",
             "BAJA": "#8B949E", "INFORMATIVA": "#6E7681"}
_COL_ESTADO_SYNC = {"SINCRONIZADA": "#3FB950", "PENDIENTE": "#F0A020", "OFFLINE": "#F85149"}


def _it(v, color=None):
    it = QTableWidgetItem("" if v is None else str(v))
    if color:
        from PyQt6.QtGui import QColor
        it.setForeground(QColor(color))
    return it


class CentroActividadWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        self.perfil = (usuario or {}).get("perfil") if isinstance(usuario, dict) else None
        self.setWindowTitle("Smart Manager — Centro de Actividad")
        self.setStyleSheet(f"background:{_BG};color:white;")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(12)

        cab = QHBoxLayout()
        t = QLabel("📡  Centro de Actividad Empresarial")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch(1)
        self.cmb_prio = _combo([("Todas las prioridades", ""), ("Crítica", "CRITICA"),
                                ("Alta", "ALTA"), ("Media", "MEDIA"), ("Baja", "BAJA"),
                                ("Informativa", "INFORMATIVA")])
        self.cmb_prio.setMinimumWidth(240)   # más ancho: los textos del desplegable no se cortan
        try:
            self.cmb_prio.view().setMinimumWidth(240)
        except Exception:
            pass
        self.cmb_prio.currentIndexChanged.connect(self._cargar)
        cab.addWidget(QLabel("Prioridad:")); cab.addWidget(self.cmb_prio)
        cab.addWidget(_btn("🔄  ACTUALIZAR", self._cargar, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver_menu))
        root.addLayout(cab)

        # ── Bloque IA (SUBFASE 8): resumen inteligente + alertas + preguntar a la IA ──
        ia_frame = QFrame()
        ia_frame.setStyleSheet(f"QFrame{{background:#111822;border:1px solid {_CIAN};border-radius:10px;}}")
        ia_ly = QVBoxLayout(ia_frame); ia_ly.setContentsMargins(14, 10, 14, 10); ia_ly.setSpacing(6)
        fila_ia = QHBoxLayout()
        lbl_ia = QLabel("🤖  Resumen inteligente del día")
        lbl_ia.setStyleSheet(f"color:{_CIAN};font-weight:bold;font-size:15px;border:none;")
        fila_ia.addWidget(lbl_ia); fila_ia.addStretch(1)
        self.in_ia = _inp("Pregunta a la IA (ej.: ¿qué productos necesitan reposición?)")
        self.in_ia.setMinimumWidth(360)
        self.in_ia.returnPressed.connect(self._preguntar_ia)
        fila_ia.addWidget(self.in_ia, 2)
        fila_ia.addWidget(_btn("PREGUNTAR", self._preguntar_ia, primary=True))
        ia_ly.addLayout(fila_ia)
        self.lbl_ia_resumen = QLabel(""); self.lbl_ia_resumen.setWordWrap(True)
        self.lbl_ia_resumen.setStyleSheet("color:#C9D1D9;border:none;")
        ia_ly.addWidget(self.lbl_ia_resumen)
        self.lbl_ia_metrics = QLabel(""); self.lbl_ia_metrics.setStyleSheet("color:#8B949E;border:none;")
        ia_ly.addWidget(self.lbl_ia_metrics)
        root.addWidget(ia_frame)

        # ── Controles avanzados (Enterprise 2): categoría + agrupación + búsqueda ──
        ctr = QHBoxLayout()
        self.cmb_cat = _combo([(c.capitalize(), c) for c in _ACT.filtros.CATEGORIAS_ORDEN])
        self.cmb_cat.setMinimumWidth(150); self.cmb_cat.currentIndexChanged.connect(self._cargar)
        ctr.addWidget(QLabel("Categoría:")); ctr.addWidget(self.cmb_cat)
        self.cmb_por = _combo([("Agrupar por tipo", "tipo"), ("por usuario", "usuario"),
                               ("por tienda", "tienda"), ("por módulo", "modulo")])
        self.cmb_por.setMinimumWidth(170); self.cmb_por.currentIndexChanged.connect(self._cargar)
        ctr.addWidget(self.cmb_por)
        ctr.addStretch(1)
        self.in_buscar = _inp("Buscar: factura, cliente, artículo, UUID, hash, terminal…")
        self.in_buscar.setMinimumWidth(340); self.in_buscar.returnPressed.connect(self._buscar)
        ctr.addWidget(self.in_buscar, 2)
        ctr.addWidget(_btn("BUSCAR", self._buscar, primary=True))
        root.addLayout(ctr)

        # ── Vista ejecutiva (SUBFASE 2.8) ──
        self.lbl_exec = QLabel(""); self.lbl_exec.setStyleSheet(f"color:{_CIAN};font-weight:bold;")
        root.addWidget(self.lbl_exec)

        # ── Timeline corporativo agrupado (doble clic: grupo → expandir · evento → historial) ──
        root.addWidget(QLabel("Línea de tiempo (grupos ▸ doble clic para expandir; evento → historial)"))
        self.tbl = _tabla(["Hora", "Terminal", "Actividad", "Detalle", "Estado", "Prioridad"])
        self.tbl.cellDoubleClicked.connect(self._ver_historial)
        root.addWidget(self.tbl, 3)

        # ── Dashboard de infraestructura (Fase 4) ──
        self.lbl_sync = QLabel("Infraestructura de sincronización")
        self.lbl_sync.setStyleSheet(f"color:{_CIAN};font-weight:bold;")
        root.addWidget(self.lbl_sync)
        self.tbl_sync = _tabla(["Terminal", "Estado", "Versión SW", "Cola pend.", "Paquetes",
                                "Bytes", "Latencia (ms)", "Última conexión"])
        root.addWidget(self.tbl_sync, 1)

        self._filas = []
        self._cargar()

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _volver_menu(self):
        if callable(self._volver):
            self._volver()

    def _cargar(self):
        cat = self.cmb_cat.currentData() or "TODOS"
        por = self.cmb_por.currentData() or "tipo"
        prio = self.cmb_prio.currentData() or None
        try:
            data = _ACT.agrupacion.feed_agrupado(self.usuario, self.perfil, self._emp(),
                                                 categoria=cat, por=por, prioridad=prio,
                                                 umbral=5, limite=200)
        except Exception as e:
            logger.error("timeline agrupado: %s", e); data = {"secciones": []}
        self._nodos = {}   # fila -> nodo (grupo/evento) para el doble clic
        self.tbl.setRowCount(0)
        for sec in data.get("secciones", []):
            self._fila_separador(sec.get("separador"))
            for nodo in sec.get("nodos", []):
                if nodo.get("kind") == "grupo":
                    self._fila_grupo(nodo)
                else:
                    self._fila_evento(nodo)
        self._cargar_sync()
        self._cargar_ia()
        self._cargar_exec()

    def _fila_separador(self, sep):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        self.tbl.setItem(r, 0, _it(""))
        self.tbl.setItem(r, 2, _it(f"— {sep} —", color=_CIAN))
        for col in (1, 3, 4, 5):
            self.tbl.setItem(r, col, _it(""))

    def _fila_grupo(self, nodo):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        prio_v = nodo.get("prioridad") or "MEDIA"
        self.tbl.setItem(r, 0, _it(str(nodo.get("fecha") or "")[11:16]))
        self.tbl.setItem(r, 1, _it("▸", color=_CIAN))
        self.tbl.setItem(r, 2, _it(nodo.get("resumen"), color=_CIAN))
        self.tbl.setItem(r, 3, _it(f"{nodo.get('count')} eventos · doble clic para expandir", color="#8B949E"))
        self.tbl.setItem(r, 4, _it(""))
        self.tbl.setItem(r, 5, _it(prio_v, color=_COL_PRIO.get(str(prio_v).upper(), "#FFFFFF")))
        self._nodos[r] = nodo

    def _fila_evento(self, f):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        prio_v = f.get("prioridad") or "MEDIA"
        self.tbl.setItem(r, 0, _it(str(f.get("fecha") or "")[11:16]))
        self.tbl.setItem(r, 1, _it(f.get("terminal")))
        self.tbl.setItem(r, 2, _it(f.get("tipo_legible")))
        self.tbl.setItem(r, 3, _it(f.get("resumen")))
        self.tbl.setItem(r, 4, _it(f.get("estado"),
                                   color=("#F0A020" if "Pendiente" in (f.get("estado") or "") else "#3FB950")))
        self.tbl.setItem(r, 5, _it(prio_v, color=_COL_PRIO.get(str(prio_v).upper(), "#FFFFFF")))
        self._nodos[r] = f

    def _cargar_exec(self):
        try:
            tarjetas = _ACT.ejecutiva.vista_ejecutiva(self._emp(), usuario=self.usuario, perfil=self.perfil)
        except Exception as e:
            logger.error("vista ejecutiva: %s", e); tarjetas = []
        flechas = {"up": "↑", "down": "↓", "flat": "→"}
        partes = [f"{c['titulo']}: {c['valor']} {flechas.get(c.get('tendencia'), '')}" for c in tarjetas]
        self.lbl_exec.setText("     ·     ".join(partes))

    def _buscar(self):
        texto = (self.in_buscar.text() or "").strip()
        if not texto:
            self._cargar(); return
        try:
            res = _ACT.busqueda.buscar_global(texto, self._emp(), usuario=self.usuario,
                                              perfil=self.perfil, limite=100)
        except Exception as e:
            logger.error("busqueda: %s", e); res = []
        self._nodos = {}
        self.tbl.setRowCount(0)
        self._fila_separador(f"Resultados de búsqueda: '{texto}' ({len(res)})")
        for f in res:
            f["terminal"] = ("CENTRAL" if str(f.get("origen")).lower() == "central"
                             else str(f.get("origen") or "-").upper())
            f["estado"] = ""
            self._fila_evento(f)

    def _cargar_ia(self):
        try:
            from src.services import ia
            p = ia.servicio().panel_centro(self._emp(), usuario=self.usuario, perfil=self.perfil)
        except Exception as e:
            logger.error("panel ia: %s", e); p = {}
        self.lbl_ia_resumen.setText(p.get("resumen") or "—")
        al = len(p.get("alertas") or []); rec = len(p.get("recomendaciones") or [])
        pen = len(p.get("pendientes") or []); pre = len(p.get("prediccion_alertas") or [])
        aut = p.get("automatizacion") or {}
        partes = []
        if al:
            partes.append(f"🔴 {al} alertas")
        if pre:
            partes.append(f"🔮 {pre} predictivas")
        if rec:
            partes.append(f"💡 {rec} recomendaciones")
        if pen:
            partes.append(f"⏳ {pen} pendientes")
        if aut.get("total"):
            partes.append(f"⚙️ {aut.get('total')} automatizaciones ({aut.get('tiempo_ahorrado_min', 0)} min ahorrados)")
        self.lbl_ia_metrics.setText("     ·     ".join(partes) or "Sin alertas ni pendientes críticos.")

    def _preguntar_ia(self):
        texto = (self.in_ia.text() or "").strip()
        if not texto:
            return
        # Enterprise 5: el Copiloto orquesta IA/Predicción/Automatización con explicabilidad.
        try:
            from src.services import copilot
            r = copilot.servicio().preguntar(texto, usuario=self.usuario, id_empresa=self._emp())
        except Exception as e:
            r = {"intent": "error", "texto": f"Error: {e}", "fuentes": []}
        lineas = [r.get("texto") or "(sin respuesta)"]
        fuentes = r.get("fuentes") or []
        if fuentes:
            lineas += ["", "Fuentes: " + ", ".join(str(f) for f in fuentes)]
        rc = r.get("recomendaciones_contextuales") or []
        if rc:
            lineas += ["", "También podrías:"]
            for x in rc[:3]:
                lineas.append(f"  · {x.get('accion')}: {x.get('motivo')}")
        if mostrar_mensaje is not None:
            mostrar_mensaje(self, "Copiloto · " + str(r.get("intent") or "respuesta"),
                            "\n".join(lineas), nivel="info")

    def _cargar_sync(self):
        try:
            infra = _ACT.sincronizacion.infraestructura(self._emp())
            filas = infra.get("terminales", [])
        except Exception as e:
            logger.error("panel sync: %s", e); filas = []
        self.tbl_sync.setRowCount(0)
        for s in filas:
            r = self.tbl_sync.rowCount(); self.tbl_sync.insertRow(r)
            est = s.get("estado") or "SINCRONIZADA"
            ult = s.get("ultima_sync") or s.get("ultima_sincronizacion")
            self.tbl_sync.setItem(r, 0, _it(s.get("nombre")))
            self.tbl_sync.setItem(r, 1, _it(est, color=_COL_ESTADO_SYNC.get(est, "#FFFFFF")))
            self.tbl_sync.setItem(r, 2, _it(s.get("version_sw") or "—"))
            self.tbl_sync.setItem(r, 3, _it(s.get("cambios_pendientes")))
            self.tbl_sync.setItem(r, 4, _it(s.get("paquetes") or 0))
            self.tbl_sync.setItem(r, 5, _it(s.get("bytes") or 0))
            self.tbl_sync.setItem(r, 6, _it(s.get("latencia_ms") or 0))
            self.tbl_sync.setItem(r, 7, _it(str(ult or "—")[:19]))

    def _ver_historial(self, row, _col):
        ev = getattr(self, "_nodos", {}).get(row)
        if ev is None:
            return
        # Grupo colapsado → EXPANDIR (mostrar sus eventos, sin perder informacion).
        if ev.get("kind") == "grupo":
            items = ev.get("items", [])
            lineas = [ev.get("resumen", ""), ""]
            for it in items[:40]:
                lineas.append(f"  · {str(it.get('fecha') or '')[11:16]}  {it.get('tipo_legible')}"
                              f"  —  {it.get('resumen') or ''}")
            if len(items) > 40:
                lineas.append(f"  … y {len(items) - 40} más")
            if mostrar_mensaje is not None:
                mostrar_mensaje(self, f"Detalle del grupo ({ev.get('count')})", "\n".join(lineas), nivel="info")
            return
        try:
            det = _ACT.historial.detalle(ev.get("id"), self._emp())
        except Exception as e:
            logger.error("historial: %s", e); det = {}
        e = det.get("evento") or {}
        lineas = [
            f"Actividad: {ev.get('tipo_legible')}",
            f"Quién: {e.get('usuario') or '—'}   ·   Desde: {(e.get('origen') or '—').upper()}",
            f"Cuándo: {str(e.get('fecha_creacion') or ev.get('fecha') or '')[:19]}",
            f"Prioridad: {e.get('prioridad') or ev.get('prioridad')}   ·   Estado: {ev.get('estado')}",
            "",
            "Distribución por terminal:",
        ]
        for d in det.get("distribucion", []):
            lineas.append(f"  · {d.get('destino')}: {d.get('estado')}"
                          + (f" (aplicado {str(d.get('fecha_confirmacion'))[:19]})" if d.get("fecha_confirmacion") else ""))
        if not det.get("distribucion"):
            lineas.append("  (aún sin distribuir)")
        msg = "\n".join(lineas)
        if mostrar_mensaje is not None:
            mostrar_mensaje(self, "Historial de la actividad", msg, nivel="info")
        else:  # pragma: no cover
            logger.info(msg)
