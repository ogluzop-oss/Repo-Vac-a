"""
Placas Antihurto (EAS) — pestaña del módulo Seguridad (junto a Cámaras, `camaras_gui.py`).

SOLO consume `src.services.eas` (inventario/mantenimiento/historial) y, de forma indirecta, la
lógica de alarma ya existente en `src.services.rfid.antihurto` (sin lógica de negocio propia aquí).
Tres secciones: inventario de antenas, mantenimiento técnico (intervenciones/calibración) e
historial de detecciones — mismo criterio de aislamiento por empresa+tienda y mismo sistema de
permisos (`eas.ver`/`eas.gestionar`) que el resto de la app.
"""

import datetime as _dt
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox, QDateTimeEdit, QDialog, QFormLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.gui.catalogo_gestion import _btn, _combo, _dialogo_frameless, _inp, _tabla
from src.gui.components import EnterpriseTabs
from src.services import autorizacion, eas

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("gui.eas")

_BG = "#0E1117"; _BG2 = "#161B22"; _CIAN = "#00FFC6"; _BORDE = "#30363D"; _TEXT = "#E6EDF3"
_DIM = "#8B949E"; _ROJO = "#F85149"; _AMBAR = "#FFB020"; _VERDE = "#2ECC71"

_ESTADO_COLOR = {"operativo": _VERDE, "mantenimiento": _AMBAR, "averiado": _ROJO,
                 "desconectado": _DIM}
_ESTADO_LABEL = {"operativo": "Operativo", "mantenimiento": "En Mantenimiento",
                 "averiado": "Averiado", "desconectado": "Desconectado"}
_TECNOLOGIA_LABEL = {"AM": "Acusto-Magnética (AM)", "RF": "Radiofrecuencia (RF)"}
_TIPO_INTERVENCION_LABEL = {
    "preventivo": "Mantenimiento Preventivo", "calibracion": "Calibración de Umbral",
    "ruido": "Análisis de Ruido Ambiental", "diagnostico": "Diagnóstico de Hardware y Firmware",
}


def _it(v, color=None):
    it = QTableWidgetItem("" if v is None else str(v))
    if color:
        it.setForeground(QColor(color))
    return it


def _info(parent, titulo, mensaje):
    if mostrar_mensaje:
        mostrar_mensaje(parent, titulo, mensaje, "info")
    else:
        logger.info("%s: %s", titulo, mensaje)


def _error(parent, titulo, mensaje):
    if mostrar_mensaje:
        mostrar_mensaje(parent, titulo, mensaje, "error")
    else:
        logger.warning("%s: %s", titulo, mensaje)


def _confirmar(parent, titulo, mensaje) -> bool:
    """Confirmación frameless (mismo criterio que el resto de la app: un QMessageBox nativo puede
    no llegar a mostrarse sobre una ventana anfitriona frameless)."""
    dlg = QDialog(parent)
    v = _dialogo_frameless(dlg, titulo, ancho=360)
    lbl = QLabel(mensaje); lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color:{_DIM};font-size:13px;")
    v.addWidget(lbl)
    fila = QHBoxLayout(); fila.addStretch()
    fila.addWidget(_btn("Confirmar", dlg.accept, danger=True))
    v.addLayout(fila)
    return dlg.exec() == QDialog.DialogCode.Accepted


def _etiqueta_campo(texto) -> QLabel:
    lab = QLabel(texto)
    lab.setStyleSheet(f"color:{_DIM};font-size:12px;")
    return lab


def _area_texto() -> QPlainTextEdit:
    t = QPlainTextEdit()
    t.setStyleSheet(f"QPlainTextEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                    f"border-radius:8px;padding:6px;font-size:12px;}}")
    t.setFixedHeight(70)
    return t


def _fecha_hora_edit() -> QDateTimeEdit:
    # Mismo diseño exacto que el desplegable "Tienda" (`_combo`, catalogo_gestion.py): alto fijo
    # 34px, mismo borde/padding, y el borde se ilumina en cian al interactuar — antes faltaba
    # altura fija y el estado activo, lo que lo hacía visualmente distinto (petición explícita).
    dt = QDateTimeEdit(_dt.datetime.now())
    dt.setCalendarPopup(True)
    dt.setDisplayFormat("dd/MM/yyyy HH:mm")
    dt.setFixedHeight(34)
    dt.setStyleSheet(
        f"QDateTimeEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
        f"border-radius:8px;padding:0 10px;font-size:12px;}}"
        f"QDateTimeEdit:hover,QDateTimeEdit:focus{{border-color:{_CIAN};}}")
    return dt


def _num_o_none(texto):
    t = (texto or "").strip().replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


# ============================================================
# Diálogos
# ============================================================
class _DispositivoDialog(QDialog):
    """Alta/edición de una antena EAS. Usa `_dialogo_frameless` (helper compartido de
    `catalogo_gestion.py`) — a diferencia del resto de `camaras_gui.py`, que predata ese helper y
    tiene su propio patrón "a mano"; para código nuevo se reutiliza el compartido."""

    def __init__(self, tiendas, dispositivo=None, parent=None):
        super().__init__(parent)
        self.resultado = None
        titulo = "Editar antena" if dispositivo else "Registrar nueva antena"
        v = _dialogo_frameless(self, titulo, ancho=420)

        self.inp_nombre = _inp("Ej. Antena Principal Entrada Norte")
        self.cmb_tienda = _combo([(t.get("nombre") or t.get("codigo_tienda") or f"Tienda {t['id']}",
                                   t["id"]) for t in tiendas])
        # `_combo` espera (etiqueta, valor) — se invierte el dict aquí.
        self.cmb_tecnologia = _combo([(lbl, cod) for cod, lbl in _TECNOLOGIA_LABEL.items()])
        self.inp_numero_serie = _inp("Opcional")
        self.inp_modelo = _inp("Opcional")

        if dispositivo:
            self.inp_nombre.setText(dispositivo.get("nombre_dispositivo") or "")
            i = self.cmb_tienda.findData(dispositivo.get("id_tienda"))
            if i >= 0:
                self.cmb_tienda.setCurrentIndex(i)
            i = self.cmb_tecnologia.findData(dispositivo.get("tecnologia"))
            if i >= 0:
                self.cmb_tecnologia.setCurrentIndex(i)
            self.inp_numero_serie.setText(dispositivo.get("numero_serie") or "")
            self.inp_modelo.setText(dispositivo.get("modelo") or "")

        form = QFormLayout(); form.setSpacing(10)
        form.addRow(_etiqueta_campo("Nombre del dispositivo"), self.inp_nombre)
        form.addRow(_etiqueta_campo("Tienda"), self.cmb_tienda)
        form.addRow(_etiqueta_campo("Tecnología"), self.cmb_tecnologia)
        form.addRow(_etiqueta_campo("Nº de serie"), self.inp_numero_serie)
        form.addRow(_etiqueta_campo("Modelo"), self.inp_modelo)
        v.addLayout(form)

        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Guardar", self._guardar, primary=True))
        v.addLayout(fila)

    def _guardar(self):
        nombre = self.inp_nombre.text().strip()
        if not nombre:
            _error(self, "Antena EAS", "El nombre del dispositivo es obligatorio.")
            return
        id_tienda = self.cmb_tienda.currentData()
        if id_tienda is None:
            _error(self, "Antena EAS", "No hay ninguna tienda disponible para asignar.")
            return
        self.resultado = {
            "nombre_dispositivo": nombre, "id_tienda": id_tienda,
            "tecnologia": self.cmb_tecnologia.currentData(),
            "numero_serie": self.inp_numero_serie.text().strip() or None,
            "modelo": self.inp_modelo.text().strip() or None,
        }
        self.accept()


class _IntervencionDialog(QDialog):
    """Registro de una intervención técnica (emulando el software de campo del técnico):
    mantenimiento preventivo, calibración de umbral, análisis de ruido o diagnóstico. La fecha se
    autocompleta con el momento actual (editable)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        v = _dialogo_frameless(self, "Registrar intervención técnica", ancho=460)

        self.cmb_tipo = _combo([(lbl, cod) for cod, lbl in _TIPO_INTERVENCION_LABEL.items()])
        self.dt_fecha = _fecha_hora_edit()
        self.inp_tecnico = _inp("Técnico responsable")
        try:
            from src.db.usuario import sesion_global
            self.inp_tecnico.setText(str((sesion_global.usuario_actual or {}).get("nombre") or ""))
        except Exception:
            pass
        self.inp_ruido = _inp("Ej. 12.5 (dB / interferencia detectada)")
        self.inp_umbral = _inp("Valor configurado en la placa")
        self.inp_firmware = _inp("Ej. v2.3.1")
        self.inp_placa = _inp("Ej. OK, revisar, sustituir")
        self.txt_obs = _area_texto()

        form = QFormLayout(); form.setSpacing(8)
        form.addRow(_etiqueta_campo("Tipo de intervención"), self.cmb_tipo)
        form.addRow(_etiqueta_campo("Fecha / hora"), self.dt_fecha)
        form.addRow(_etiqueta_campo("Técnico responsable"), self.inp_tecnico)
        form.addRow(_etiqueta_campo("Nivel de ruido ambiental"), self.inp_ruido)
        form.addRow(_etiqueta_campo("Umbral de sensibilidad"), self.inp_umbral)
        form.addRow(_etiqueta_campo("Versión de firmware"), self.inp_firmware)
        form.addRow(_etiqueta_campo("Estado de la placa base"), self.inp_placa)
        v.addLayout(form)
        v.addWidget(_etiqueta_campo("Observaciones técnicas"))
        v.addWidget(self.txt_obs)

        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Guardar", self._guardar, primary=True))
        v.addLayout(fila)

    def _guardar(self):
        self.resultado = {
            "tipo_intervencion": self.cmb_tipo.currentData(),
            "fecha_intervencion": self.dt_fecha.dateTime().toPyDateTime(),
            "tecnico_responsable": self.inp_tecnico.text().strip() or None,
            "nivel_ruido_ambiental": _num_o_none(self.inp_ruido.text()),
            "umbral_sensibilidad": _num_o_none(self.inp_umbral.text()),
            "version_firmware": self.inp_firmware.text().strip() or None,
            "estado_placa_base": self.inp_placa.text().strip() or None,
            "observaciones": self.txt_obs.toPlainText().strip() or None,
        }
        self.accept()


# ============================================================
# Pestaña principal (contenedora de las 3 secciones)
# ============================================================
class EASTabWidget(QWidget):
    def __init__(self, usuario=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self._dispositivos = []
        self._disp_sel_id = None
        self._intervenciones = []
        self._alertas = []
        self.setStyleSheet(f"background:{_BG};")
        self._tiendas_cache = self._tiendas()
        self._build()

    # ── contexto ──────────────────────────────────────────────────────────────
    def _puede(self, permiso) -> bool:
        try:
            return bool(autorizacion.puede(self.usuario, permiso))
        except Exception:
            return False

    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _tiendas(self):
        try:
            from src.db import tiendas as _tdb
            return _tdb.listar_tiendas(self._id_empresa())
        except Exception:
            return []

    def _nombre_tienda(self, id_tienda):
        for t in self._tiendas_cache:
            if t.get("id") == id_tienda:
                return t.get("nombre") or t.get("codigo_tienda") or str(id_tienda)
        return str(id_tienda) if id_tienda is not None else "—"

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(10)
        if not self._puede("eas.ver"):
            lbl = QLabel("No tienes permiso para ver Placas Antihurto (EAS).")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color:{_DIM};font-size:14px;")
            root.addWidget(lbl, 1)
            return
        sub = EnterpriseTabs()
        sub.addTab(self._tab_inventario(), "Inventario de antenas")
        sub.addTab(self._tab_mantenimiento(), "Mantenimiento técnico")
        sub.addTab(self._tab_historial(), "Historial de detecciones")
        root.addWidget(sub)

    # ── A) Inventario ─────────────────────────────────────────────────────────
    def _tab_inventario(self) -> QWidget:
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10)

        filtros = QHBoxLayout()
        self.cmb_f_tienda = _combo([("Todas las tiendas", None)]
                                   + [(t.get("nombre") or t.get("codigo_tienda"), t["id"])
                                      for t in self._tiendas_cache])
        # Ensancha al contenido real (nombres de tienda largos se recortaban con el ancho por
        # defecto de Qt) — petición explícita.
        self.cmb_f_tienda.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.cmb_f_tienda.setMinimumWidth(170)
        self.cmb_f_tienda.currentIndexChanged.connect(self._refrescar_inventario)
        self.cmb_f_estado = _combo([("Todos los estados", None)]
                                   + [(lbl, cod) for cod, lbl in _ESTADO_LABEL.items()])
        self.cmb_f_estado.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.cmb_f_estado.setMinimumWidth(170)
        self.cmb_f_estado.currentIndexChanged.connect(self._refrescar_inventario)
        filtros.addWidget(_etiqueta_campo("Tienda"))
        filtros.addWidget(self.cmb_f_tienda)
        filtros.addWidget(_etiqueta_campo("Estado"))
        filtros.addWidget(self.cmb_f_estado)
        filtros.addStretch()
        if self._puede("eas.gestionar"):
            filtros.addWidget(_btn("🔍  Programar Mantenimiento / Diagnóstico",
                                   self._programar_mantenimiento))
            filtros.addWidget(_btn("➕  Registrar Nueva Antena", self._alta_dispositivo,
                                   primary=True))
        ly.addLayout(filtros)

        self.tbl_inventario = _tabla(["Dispositivo", "Tienda", "Tecnología", "Nº serie", "Estado",
                                      "Última revisión", "Próxima revisión"])
        self.tbl_inventario.itemSelectionChanged.connect(self._on_disp_seleccionado)
        ly.addWidget(self.tbl_inventario, 1)

        acciones = QHBoxLayout()
        if self._puede("eas.gestionar"):
            acciones.addWidget(_btn("✏️  Editar", self._editar_dispositivo, primary=True))
            acciones.addWidget(_btn("🗑️  Eliminar", self._eliminar_dispositivo, danger=True))
        acciones.addStretch()
        ly.addLayout(acciones)

        self._refrescar_inventario()
        return w

    def _refrescar_inventario(self):
        id_tienda = self.cmb_f_tienda.currentData() if hasattr(self, "cmb_f_tienda") else None
        estado = self.cmb_f_estado.currentData() if hasattr(self, "cmb_f_estado") else None
        self._dispositivos = eas.listar_dispositivos(self._id_empresa(), id_tienda, estado=estado)
        t = self.tbl_inventario
        t.setRowCount(len(self._dispositivos))
        for i, d in enumerate(self._dispositivos):
            color = _ESTADO_COLOR.get(d.get("estado_operativo"), _DIM)
            t.setItem(i, 0, _it(d.get("nombre_dispositivo")))
            t.setItem(i, 1, _it(self._nombre_tienda(d.get("id_tienda"))))
            t.setItem(i, 2, _it(_TECNOLOGIA_LABEL.get(d.get("tecnologia"), d.get("tecnologia"))))
            t.setItem(i, 3, _it(d.get("numero_serie") or "—"))
            t.setItem(i, 4, _it(_ESTADO_LABEL.get(d.get("estado_operativo"), "—"), color=color))
            t.setItem(i, 5, _it(d.get("ultima_revision") or "—"))
            prox = d.get("proxima_revision_recomendada")
            vencida = bool(prox) and prox <= _dt.date.today()
            t.setItem(i, 6, _it(prox or "Sin programar",
                                color=_ROJO if (vencida or not prox) else None))

    def _disp_sel(self):
        i = self.tbl_inventario.currentRow()
        return self._dispositivos[i] if 0 <= i < len(self._dispositivos) else None

    def _on_disp_seleccionado(self):
        d = self._disp_sel()
        self._disp_sel_id = d["id"] if d else None
        if hasattr(self, "lbl_mant_dispositivo"):
            self._refrescar_mantenimiento()

    def _alta_dispositivo(self):
        if not self._tiendas_cache:
            _error(self, "Antena EAS", "No hay tiendas dadas de alta para asignar la antena.")
            return
        dlg = _DispositivoDialog(self._tiendas_cache, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.resultado:
            did = eas.crear_dispositivo(dlg.resultado["nombre_dispositivo"],
                                        dlg.resultado["id_tienda"], id_empresa=self._id_empresa(),
                                        tecnologia=dlg.resultado["tecnologia"],
                                        numero_serie=dlg.resultado["numero_serie"],
                                        modelo=dlg.resultado["modelo"])
            if did:
                _info(self, "Antena EAS", "Dispositivo registrado correctamente.")
                self._refrescar_inventario()
            else:
                _error(self, "Antena EAS", "No se pudo registrar el dispositivo.")

    def _editar_dispositivo(self):
        d = self._disp_sel()
        if not d:
            _info(self, "Antena EAS", "Selecciona una antena.")
            return
        dlg = _DispositivoDialog(self._tiendas_cache, dispositivo=d, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.resultado:
            ok = eas.actualizar_dispositivo(d["id"], id_empresa=self._id_empresa(),
                                            **dlg.resultado)
            if ok:
                _info(self, "Antena EAS", "Dispositivo actualizado.")
                self._refrescar_inventario()
            else:
                _error(self, "Antena EAS", "No se pudo actualizar el dispositivo.")

    def _eliminar_dispositivo(self):
        d = self._disp_sel()
        if not d:
            _info(self, "Antena EAS", "Selecciona una antena.")
            return
        if not _confirmar(self, "Eliminar antena",
                          f"¿Seguro que quieres eliminar \"{d.get('nombre_dispositivo')}\"? "
                          "Se perderá su historial de mantenimiento."):
            return
        if eas.eliminar_dispositivo(d["id"], id_empresa=self._id_empresa()):
            self._refrescar_inventario()
        else:
            _error(self, "Antena EAS", "No se pudo eliminar el dispositivo.")

    def _programar_mantenimiento(self):
        """Atajo: registra una intervención directamente desde el inventario (equivale a
        seleccionar la antena en la pestaña Mantenimiento técnico y pulsar "Registrar
        intervención")."""
        d = self._disp_sel()
        if not d:
            _info(self, "Antena EAS", "Selecciona primero la antena a revisar.")
            return
        self._registrar_intervencion_para(d)

    # ── B) Mantenimiento técnico ──────────────────────────────────────────────
    def _tab_mantenimiento(self) -> QWidget:
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10)

        fila = QHBoxLayout()
        self.lbl_mant_dispositivo = QLabel("Selecciona una antena en «Inventario de antenas» "
                                           "para ver/registrar sus intervenciones.")
        self.lbl_mant_dispositivo.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        self.lbl_mant_dispositivo.setWordWrap(True)
        fila.addWidget(self.lbl_mant_dispositivo, 1)
        if self._puede("eas.gestionar"):
            fila.addWidget(_btn("🛠️  Registrar intervención", self._nueva_intervencion,
                                primary=True))
        ly.addLayout(fila)

        self.tbl_intervenciones = _tabla(["Fecha", "Tipo", "Técnico", "Ruido amb.", "Umbral",
                                          "Firmware", "Placa base", "Observaciones"])
        ly.addWidget(self.tbl_intervenciones, 1)
        return w

    def _refrescar_mantenimiento(self):
        d = next((x for x in self._dispositivos if x["id"] == self._disp_sel_id), None)
        if not d:
            self.lbl_mant_dispositivo.setText("Selecciona una antena en «Inventario de antenas» "
                                              "para ver/registrar sus intervenciones.")
            self.tbl_intervenciones.setRowCount(0)
            return
        self.lbl_mant_dispositivo.setText(
            f"{d.get('nombre_dispositivo')} · {self._nombre_tienda(d.get('id_tienda'))}")
        self._intervenciones = eas.listar_intervenciones(d["id"], id_empresa=self._id_empresa())
        t = self.tbl_intervenciones
        t.setRowCount(len(self._intervenciones))
        for i, iv in enumerate(self._intervenciones):
            t.setItem(i, 0, _it(iv.get("fecha_intervencion")))
            t.setItem(i, 1, _it(_TIPO_INTERVENCION_LABEL.get(iv.get("tipo_intervencion"),
                                                             iv.get("tipo_intervencion"))))
            t.setItem(i, 2, _it(iv.get("tecnico_responsable") or "—"))
            t.setItem(i, 3, _it(iv.get("nivel_ruido_ambiental") if iv.get("nivel_ruido_ambiental")
                                is not None else "—"))
            t.setItem(i, 4, _it(iv.get("umbral_sensibilidad") if iv.get("umbral_sensibilidad")
                                is not None else "—"))
            t.setItem(i, 5, _it(iv.get("version_firmware") or "—"))
            t.setItem(i, 6, _it(iv.get("estado_placa_base") or "—"))
            t.setItem(i, 7, _it(iv.get("observaciones") or "—"))

    def _nueva_intervencion(self):
        d = next((x for x in self._dispositivos if x["id"] == self._disp_sel_id), None)
        if not d:
            _info(self, "Mantenimiento EAS", "Selecciona primero una antena en el inventario.")
            return
        self._registrar_intervencion_para(d)

    def _registrar_intervencion_para(self, dispositivo):
        dlg = _IntervencionDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.resultado:
            iid = eas.registrar_intervencion(dispositivo["id"], dlg.resultado["tipo_intervencion"],
                                             id_empresa=self._id_empresa(), **{
                                                 k: v for k, v in dlg.resultado.items()
                                                 if k != "tipo_intervencion"})
            if iid:
                _info(self, "Mantenimiento EAS", "Intervención registrada. Próxima revisión "
                                                  "recalculada automáticamente si procedía.")
                self._refrescar_inventario()
                self._refrescar_mantenimiento()
            else:
                _error(self, "Mantenimiento EAS", "No se pudo registrar la intervención.")

    # ── C) Historial de detecciones ───────────────────────────────────────────
    def _tab_historial(self) -> QWidget:
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10)

        filtros = QHBoxLayout()
        self.cmb_h_tienda = _combo([("Todas las tiendas", None)]
                                   + [(t.get("nombre") or t.get("codigo_tienda"), t["id"])
                                      for t in self._tiendas_cache])
        self.cmb_h_tienda.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.cmb_h_tienda.setMinimumWidth(170)
        self.cmb_h_tienda.currentIndexChanged.connect(self._refrescar_historial)
        self.dt_h_desde = _fecha_hora_edit()
        self.dt_h_desde.setDateTime(_dt.datetime.now() - _dt.timedelta(days=30))
        self.dt_h_hasta = _fecha_hora_edit()
        filtros.addWidget(_etiqueta_campo("Tienda"))
        filtros.addWidget(self.cmb_h_tienda)
        filtros.addWidget(_etiqueta_campo("Desde"))
        filtros.addWidget(self.dt_h_desde)
        filtros.addWidget(_etiqueta_campo("Hasta"))
        filtros.addWidget(self.dt_h_hasta)
        filtros.addWidget(_btn("Filtrar", self._refrescar_historial, primary=True))
        filtros.addStretch()
        ly.addLayout(filtros)

        self.tbl_historial = _tabla(["Fecha / hora", "Tienda", "Artículo", "Guardias "
                                     "notificados", "Push entregado"])
        ly.addWidget(self.tbl_historial, 1)

        self._refrescar_historial()
        return w

    def _refrescar_historial(self):
        id_tienda = self.cmb_h_tienda.currentData() if hasattr(self, "cmb_h_tienda") else None
        desde = self.dt_h_desde.dateTime().toPyDateTime() if hasattr(self, "dt_h_desde") else None
        hasta = self.dt_h_hasta.dateTime().toPyDateTime() if hasattr(self, "dt_h_hasta") else None
        self._alertas = eas.listar_alertas(self._id_empresa(), id_tienda, desde=desde, hasta=hasta)
        t = self.tbl_historial
        t.setRowCount(len(self._alertas))
        for i, a in enumerate(self._alertas):
            t.setItem(i, 0, _it(a.get("timestamp_alerta")))
            t.setItem(i, 1, _it(self._nombre_tienda(a.get("id_tienda"))))
            nombre_art = a.get("articulo_nombre") or a.get("articulo_codigo") or "—"
            t.setItem(i, 2, _it(nombre_art))
            t.setItem(i, 3, _it(a.get("guardias_notificados")))
            entregado = bool(a.get("push_entregado"))
            t.setItem(i, 4, _it("Sí" if entregado else "No",
                                color=_VERDE if entregado else _AMBAR))
