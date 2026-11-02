"""
Business Intelligence — cuadro de mando (FASE BI-14).

Pantalla NUEVA. Muestra los KPIs por dominio (calculados al vuelo reutilizando el motor BI),
con filtro de periodo, forecasting de liquidez y exportación. Estilo dark+cian; empresa activa.
"""

import datetime as _dt
import logging

from PyQt6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMessageBox, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from assets.estilo_global import mostrar_mensaje
from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _btn_x, _combo, _tabla
from src.services.bi import dashboard as _D
from src.services.bi import kpis as _K

logger = logging.getLogger("bi.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class BIDashboardWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main   # menú principal (para navegar a Documentos)
        self.setStyleSheet(f"background:{_BG};")
        try:
            _K.sincronizar_definiciones()
        except Exception:
            pass
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Business Intelligence · Cuadro de mando")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        self.cmb_periodo = _combo([("Mes", "mes"), ("Semana", "semana"), ("Día", "dia"), ("Año", "anio")])
        self.cmb_periodo.setMinimumWidth(150)   # evita texto cortado en el desplegable
        cab.addWidget(QLabel("Periodo:")); cab.addWidget(self.cmb_periodo)
        # `lambda: self._load()` (no conectar `self._load` directamente): la señal `clicked(bool)`
        # de Qt pasa su `checked` POSICIONALMENTE al único parámetro del slot (`avisar`), así que un
        # `_btn(txt, self._load, ...)` directo dejaba `avisar` siempre en `False` en cada click real
        # — el aviso de éxito/error nunca se mostraba (bug real, ya corregido). `_btn_cargando` no
        # tenía este problema porque su wrapper interno ya llama a `cb()` sin argumentos.
        cab.addWidget(_btn("Calcular", lambda: self._load(), primary=True))
        cab.addWidget(_btn("Exportar Excel", self._exportar_excel, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tbl = _tabla(["Dominio", "KPI", "Valor", "Unidad"])
        root.addWidget(self.tbl)

        # Ventas por FAMILIA de producto (últimos 30 días) — reutiliza db/familias.ventas_por_familia.
        self.lbl_fam = QLabel("Ventas por familia · últimos 30 días")
        self.lbl_fam.setStyleSheet(f"color:{_CIAN};font-weight:bold;")
        root.addWidget(self.lbl_fam)
        self.tbl_fam = _tabla(["Familia", "Unidades", "Importe (€)"])
        root.addWidget(self.tbl_fam)

        # Mensaje de éxito + "Ver archivo" tras exportar (oculto hasta exportar).
        self.lbl_export = QLabel(""); self.lbl_export.setWordWrap(True)
        self.lbl_export.setStyleSheet(f"color:{_CIAN};font-weight:bold;")
        self.lbl_export.setVisible(False)
        root.addWidget(self.lbl_export)
        self.btn_ver = _btn("📂 VER ARCHIVO", self._abrir_documentos_exportaciones, primary=True)
        self.btn_ver.setVisible(False)
        _fila_ver = QHBoxLayout(); _fila_ver.addStretch(); _fila_ver.addWidget(self.btn_ver); _fila_ver.addStretch()
        root.addLayout(_fila_ver)

        self._dash = None
        self._load(avisar=False)

    def _load(self, avisar=True):
        """`avisar=False` en la carga inicial del `__init__` (no es una acción del usuario, no debe
        mostrar un aviso emergente) — mismo criterio que `tesoreria_gui.py::_load_cashflow`. El botón
        'Calcular' y el resto de llamadas interactivas usan el valor por defecto `avisar=True`."""
        try:
            per = self.cmb_periodo.currentData() or "mes"
            self._dash = _D.panel(_empresa(), periodo=per, con_forecast=True)
            filas = []
            for dom, items in self._dash["secciones"].items():
                for it in items:
                    filas.append((dom, it["nombre"], it["valor"], it.get("unidad")))
            self.tbl.setRowCount(len(filas))
            for i, (dom, nom, val, u) in enumerate(filas):
                for j, v in enumerate([dom, nom, f"{float(val):,.2f}", u]):
                    self.tbl.setItem(i, j, _it(v))
            self.lbl.setStyleSheet(f"color:{_DIM};")
            self.lbl.setText("Cuadro de mando actualizado.")
            fl = self._dash.get("forecast_liquidez", {})
            if fl.get("proyecciones"):
                p90 = next((p for p in fl["proyecciones"] if p["horizonte_dias"] == 90), None)
                if p90:
                    self.lbl.setText(f"Liquidez estimada a 90 días: {p90['liquidez_estimada']:.2f} €")
            if avisar:
                if filas:
                    mostrar_mensaje(self, "Cuadro de mando", "Cuadro de mando calculado correctamente.",
                                    nivel="success")
                else:
                    mostrar_mensaje(self, "Cuadro de mando",
                                    "Cálculo realizado, pero no hay KPIs para el periodo seleccionado.",
                                    nivel="info")
        except Exception as e:
            logger.error("load: %s", e)
            self.lbl.setStyleSheet("color:#F85149;font-weight:bold;")
            self.lbl.setText(f"Error al calcular el cuadro de mando: {e}")
            if avisar:
                mostrar_mensaje(self, "Cuadro de mando", f"No se pudo calcular el cuadro de mando: {e}",
                                nivel="error")
        self._load_familias()

    def _load_familias(self):
        """Rellena la tabla de ventas por familia (degradable: si no hay datos, queda vacía)."""
        try:
            from src.db.familias import ventas_por_familia
            filas = ventas_por_familia(_empresa(), dias=30)
            self.tbl_fam.setRowCount(len(filas))
            for i, r in enumerate(filas):
                self.tbl_fam.setItem(i, 0, _it(r.get("familia")))
                self.tbl_fam.setItem(i, 1, _it(f"{int(r.get('unidades') or 0)}"))
                self.tbl_fam.setItem(i, 2, _it(f"{float(r.get('importe') or 0):,.2f}"))
        except Exception as e:
            logger.error("load_familias: %s", e)

    def _exportar_excel(self):
        """Exporta el cuadro de mando a Excel, lo registra en Documentos → Exportaciones
        Excel y ofrece un botón 'Ver archivo' para ir allí."""
        if not self._dash:
            self._load()
        if not self._dash:
            return
        try:
            # Exportación unificada (Enterprise Foundation): un único helper para todo el ERP.
            filas = []
            for dom, items in self._dash["secciones"].items():
                for it in items:
                    filas.append({"Dominio": dom, "KPI": it["nombre"],
                                  "Valor": it["valor"], "Unidad": it.get("unidad") or ""})
            from src.gui.foundation.export import exportar_excel
            res = exportar_excel(filas, "Cuadro_Mando", columnas=["Dominio", "KPI", "Valor", "Unidad"],
                                 hoja="Cuadro de mando", referencia="CUADRO_MANDO")
            if not res["ok"]:
                raise RuntimeError(res.get("error") or "exportación fallida")
            registrado = res["registrado"]
        except Exception as e:
            self.lbl_export.setStyleSheet("color:#F85149;font-weight:bold;")
            self.lbl_export.setText(f"Error al exportar: {e}")
            self.lbl_export.setVisible(True); self.btn_ver.setVisible(False)
            return
        self.lbl_export.setStyleSheet(f"color:{_CIAN};font-weight:bold;")
        self.lbl_export.setText(
            "El cuadro de mando se ha exportado correctamente.\n"
            "Puedes encontrar el archivo en la pestaña «Exportaciones Excel» de la función Documentos.")
        self.lbl_export.setVisible(True); self.btn_ver.setVisible(registrado)

    def _abrir_documentos_exportaciones(self):
        from src.gui.centro_documental import CentroDocumentalWindow
        main = getattr(self, "main", None)
        try:
            if main is not None and hasattr(main, "manejar_apertura"):
                main.manejar_apertura(
                    "documentos", CentroDocumentalWindow,
                    callback_vuelta=getattr(main, "mostrar_menu_principal", None),
                    usuario=self.usuario, categoria_inicial="exportacion")
            else:
                self._doc_win = CentroDocumentalWindow(usuario=self.usuario, categoria_inicial="exportacion")
                # Ventana hija abierta fuera de manejar_apertura: sin este flag se ve con la
                # barra de título nativa de Windows (inconsistente con el resto de módulos,
                # todos frameless). Replica el mismo tratamiento + animación de deslizamiento.
                try:
                    from PyQt6.QtCore import Qt
                    self._doc_win.setWindowFlags(
                        self._doc_win.windowFlags() | Qt.WindowType.FramelessWindowHint)
                except Exception:
                    pass
                snap = None
                try:
                    from src.gui.transiciones import capturar_pantalla
                    snap = capturar_pantalla(self)
                except Exception:
                    pass
                try:
                    from PyQt6.QtWidgets import QApplication
                    self._doc_win.setWindowOpacity(0.0)
                    scr = self._doc_win.screen() or QApplication.primaryScreen()
                    if scr is not None:
                        self._doc_win.setGeometry(scr.availableGeometry())
                except Exception:
                    pass
                self._doc_win.showMaximized()
                try:
                    from PyQt6.QtWidgets import QApplication
                    QApplication.processEvents()
                except Exception:
                    pass
                try:
                    from src.gui.transiciones import deslizar_entrada_modulo
                    deslizar_entrada_modulo(snap, self._doc_win, revelar=self._doc_win)
                except Exception:
                    try:
                        self._doc_win.setWindowOpacity(1.0)
                    except Exception:
                        pass
        except Exception as e:
            self.lbl_export.setStyleSheet("color:#F85149;font-weight:bold;")
            self.lbl_export.setText(f"No se pudo abrir Documentos: {e}")
            self.lbl_export.setVisible(True)
