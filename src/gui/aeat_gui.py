"""
Modelos AEAT — interfaz (FASE AEAT-1).

Pantalla NUEVA (no modifica las existentes). En esta fase cubre el Modelo 303: selección de
ejercicio/periodo, generación (borrador por casillas + PDF), consulta y exportación JSON/CSV.
Estilo coherente con el ERP (dark + cian). Acotada a la empresa activa.
"""

import datetime as _dt
import logging
import os

from PyQt6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMessageBox, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _btn_x, _combo, _inp, _tabla
from src.services.aeat import base as _B
from src.services.aeat import estados as _E
from src.services.aeat import exportacion as _X
from src.services.aeat import modelo_303 as _M303
from src.services.aeat import modelo_390 as _M390
from src.services.aeat import modelo_111 as _M111
from src.services.aeat import modelo_130 as _M130
from src.services.aeat import modelo_190 as _M190
from src.services.aeat import modelo_347 as _M347
from src.services.aeat import modelo_349 as _M349

logger = logging.getLogger("aeat.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class AEATWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self._sel_id = None
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("Modelos AEAT · IVA (303/390) · Pago fraccionado (130) · Retenciones (111/190) · "
                   "Terceros (347) · Intracom (349)")
        t.setStyleSheet(f"color:{_CIAN};font-size:18px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        bar = QHBoxLayout()
        self.cmb_modelo = _combo([("303", "303"), ("390", "390"), ("130", "130"), ("111", "111"),
                                  ("190", "190"), ("347", "347"), ("349", "349")])
        # El ancho por defecto (sizeHint calculado por Qt) no reserva espacio de sobra para la
        # flecha del desplegable (`::drop-down{width:22px}` fijado por el QSS de `_combo`, que Qt
        # no conoce al calcular su propio sizeHint) — el último dígito de "349"/"347"/"390" quedaba
        # recortado bajo la flecha. Todas las opciones miden igual (3 caracteres), así que un ancho
        # mínimo fijo que le dé margen de sobra basta (no hace falta medir texto por texto).
        self.cmb_modelo.setMinimumWidth(90)
        self.cmb_modelo.currentIndexChanged.connect(self._sync_modelo)
        self.in_ej = _inp("Ejercicio"); self.in_ej.setFixedWidth(90)
        self.in_ej.setText(str(_dt.date.today().year))
        self.cmb_per = _combo([(p, p) for p in _M303.periodos_validos()])
        bar.addWidget(QLabel("Modelo:")); bar.addWidget(self.cmb_modelo)
        bar.addWidget(QLabel("Ejercicio:")); bar.addWidget(self.in_ej)
        bar.addWidget(QLabel("Periodo:")); bar.addWidget(self.cmb_per)
        bar.addWidget(_btn("Generar", self._generar, primary=True))
        bar.addWidget(_btn("Ver", self._ver, primary=True))
        bar.addWidget(_btn("Exportar JSON", lambda: self._exportar("json"), primary=True))
        bar.addWidget(_btn("Exportar CSV", lambda: self._exportar("csv"), primary=True))
        self.btn_presentado = _btn("Marcar como presentado", self._marcar_presentado, primary=True)
        bar.addWidget(self.btn_presentado)
        bar.addStretch()
        root.addLayout(bar)

        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_CIAN};font-size:14px;")
        root.addWidget(self.lbl)

        self._sel_estado = None
        self._actualizar_boton_presentado()

        cuerpo = QHBoxLayout()
        self.tbl_decl = _tabla(["ID", "Modelo", "Ejercicio", "Periodo", "Estado", "Resultado"])
        self.tbl_decl.cellClicked.connect(self._sel_decl)
        cuerpo.addWidget(self.tbl_decl, 1)
        self.tbl_cas = _tabla(["Casilla", "Descripción", "Importe"])
        cuerpo.addWidget(self.tbl_cas, 1)
        root.addLayout(cuerpo)

        self._load_decl()

    def _sync_modelo(self):
        """390 y 190 son anuales: fuerzan periodo 0A y deshabilitan el selector de periodo.
        El 130 (FASE B) es SIEMPRE trimestral (nunca mensual ni anual): si el periodo actual
        no es un trimestre válido, se fuerza a 1T."""
        modelo = self.cmb_modelo.currentData()
        es_anual = modelo in ("390", "190", "347", "349")
        self.cmb_per.setEnabled(not es_anual)
        if es_anual:
            i = self.cmb_per.findData("0A")
            if i >= 0:
                self.cmb_per.setCurrentIndex(i)
        elif modelo == "130" and self.cmb_per.currentData() not in _M130.periodos_validos():
            i = self.cmb_per.findData("1T")
            if i >= 0:
                self.cmb_per.setCurrentIndex(i)

    def _load_decl(self):
        try:
            filas = _B.listar_declaraciones(id_empresa=_empresa())
            self.tbl_decl.setRowCount(len(filas))
            for i, d in enumerate(filas):
                for j, v in enumerate([d["id"], d["modelo"], d["ejercicio"], d["periodo"],
                                       d["estado"], f"{float(d['resultado']):.2f}"]):
                    self.tbl_decl.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("load_decl: %s", e)

    def _generar(self):
        try:
            ej = int(self.in_ej.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "AEAT", "Ejercicio inválido"); return
        modelo = self.cmb_modelo.currentData()
        per = "0A" if modelo in ("390", "190", "347", "349") else self.cmb_per.currentData()
        try:
            if modelo == "390":
                res = _M390.generar(ej, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            elif modelo == "349":
                res = _M349.generar(ej, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            elif modelo == "347":
                res = _M347.generar(ej, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            elif modelo == "190":
                res = _M190.generar(ej, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            elif modelo == "111":
                res = _M111.generar(ej, per, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            elif modelo == "130":
                res = _M130.generar(ej, per, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            else:
                res = _M303.generar(ej, per, id_empresa=_empresa(), usuario=self.usuario.get("nombre"))
            if not res.get("ok"):
                QMessageBox.warning(self, "AEAT", res.get("errores", "No se pudo generar")); return
            self._sel_id = res["id"]
            self._sel_estado = _E.GENERADO
            self.lbl.setText(f"{modelo} {ej}/{per} generado · Resultado: {res['resultado']:.2f} € "
                             f"({res['sentido']}){'  · PDF ✔' if res.get('pdf') else ''}")
            self._load_decl(); self._mostrar_casillas(res["casillas"])
            self._actualizar_boton_presentado()
        except Exception as e:
            QMessageBox.warning(self, "AEAT", str(e))

    def _sel_decl(self, row, _col):
        try:
            self._sel_id = int(self.tbl_decl.item(row, 0).text())
            self._sel_estado = self.tbl_decl.item(row, 4).text()
        except Exception:
            self._sel_id = None
            self._sel_estado = None
        self._actualizar_boton_presentado()

    def _ver(self):
        if not self._sel_id:
            QMessageBox.information(self, "AEAT", "Selecciona o genera una declaración."); return
        d = _B.obtener_declaracion(self._sel_id, id_empresa=_empresa())
        if d:
            self._sel_estado = d["estado"]
            self.lbl.setText(f"{d['modelo']} {d['ejercicio']}/{d['periodo']} [{d['estado']}] · "
                             f"Resultado: {float(d['resultado']):.2f} €")
            self._mostrar_casillas(d.get("casillas", []))
            self._actualizar_boton_presentado()

    def _actualizar_boton_presentado(self):
        """El botón solo se muestra cuando la declaración seleccionada está en GENERADO
        (única transición válida hacia PRESENTADO desde la UI) y el usuario tiene el
        permiso `aeat.presentar`; oculto/deshabilitado en cualquier otro caso."""
        visible = bool(self._sel_id) and self._sel_estado == _E.GENERADO
        self.btn_presentado.setVisible(visible)
        if visible:
            try:
                from src.services import autorizacion
                self.btn_presentado.setEnabled(
                    autorizacion.puede(self.usuario or {}, "aeat.presentar", id_empresa=_empresa()))
            except Exception:
                self.btn_presentado.setEnabled(True)

    def _marcar_presentado(self):
        """Botón 'Marcar como presentado' (FASE B): activa la transición GENERADO→PRESENTADO
        que YA EXISTE en `services/aeat/estados.py`/`base.cambiar_estado` pero que hasta
        ahora ningún botón de la interfaz disparaba. NO envía nada a la AEAT — Smart Manager
        no presenta modelos trimestrales/anuales de forma telemática (ese desarrollo, aparte
        y ajeno al motor Verifactu, no está en alcance); esto certifica que el usuario YA
        presentó el modelo por su cuenta en la Sede Electrónica de la AEAT, replicando el
        mismo lenguaje honesto ya usado en los diálogos de envío de Verifactu/Facturae
        (`gui/fiscal_gui.py`): nunca se simula un 'presentado' que no ha ocurrido de verdad."""
        if not self._sel_id or self._sel_estado != _E.GENERADO:
            QMessageBox.information(
                self, "AEAT",
                "Solo se puede marcar como presentada una declaración GENERADA (ni un borrador "
                "ni una ya presentada/anulada)."); return
        try:
            from src.services import autorizacion
            if not autorizacion.puede(self.usuario or {}, "aeat.presentar", id_empresa=_empresa()):
                QMessageBox.warning(self, "AEAT", "Permiso requerido: aeat.presentar"); return
        except Exception:
            pass
        r = QMessageBox.question(
            self, "Marcar como presentado",
            "Esta acción NO envía nada a la AEAT: Smart Manager no presenta modelos "
            "trimestrales/anuales de forma telemática. Al confirmar, estás CERTIFICANDO que "
            "YA has presentado tú mismo (o tu asesoría) este modelo en la Sede Electrónica de "
            "la AEAT, por tu cuenta.\n\n¿Confirmas que ya lo has presentado?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            ok = _B.cambiar_estado(self._sel_id, _E.PRESENTADO,
                                   usuario=self.usuario.get("nombre"), id_empresa=_empresa())
            if ok:
                self._sel_estado = _E.PRESENTADO
                self.lbl.setText("Declaración marcada como PRESENTADA (autocertificación del usuario; "
                                 "no se ha enviado nada a la AEAT).")
                self._load_decl(); self._actualizar_boton_presentado()
            else:
                QMessageBox.warning(self, "AEAT", "No se pudo actualizar el estado.")
        except Exception as e:
            QMessageBox.warning(self, "AEAT", str(e))

    def _mostrar_casillas(self, casillas):
        self.tbl_cas.setRowCount(len(casillas))
        for i, c in enumerate(casillas):
            for j, v in enumerate([c["casilla"], c.get("descripcion"), f"{float(c['importe']):.2f}"]):
                self.tbl_cas.setItem(i, j, _it(v))

    def _exportar(self, fmt):
        if not self._sel_id:
            QMessageBox.information(self, "AEAT", "Selecciona o genera una declaración."); return
        d = _B.obtener_declaracion(self._sel_id, id_empresa=_empresa())
        if not d:
            return
        contenido = _X.a_json(d) if fmt == "json" else _X.a_csv(d)
        sugerido = f"303_{d['ejercicio']}_{d['periodo']}.{fmt}"
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar", sugerido,
                                              f"{fmt.upper()} (*.{fmt})")
        if ruta:
            try:
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(contenido)
                QMessageBox.information(self, "AEAT", f"Exportado a {os.path.basename(ruta)}")
            except Exception as e:
                QMessageBox.warning(self, "AEAT", str(e))
