"""
Migración de datos — asistente Enterprise (Fase 2). SOLO orquesta `services.importacion` (sin lógica de
negocio, regla del proyecto). Asistente de 3 pasos: 1) fichero → 2) confirmar mapeo (auto-sugerido, IA
opcional) → 3) simulación (dry-run) + importar. Construido sobre `QtEnterpriseWindow`.
"""

import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

from src.gui.foundation import tokens as T
from src.gui.foundation.shell import QtEnterpriseWindow
from src.services import importacion as _imp
from src.services.importacion import modelo as _modelo

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("gui.migracion")

# Etiqueta visible por campo canónico (los campos de cada entidad los define `modelo.CAMPOS`).
_ETIQUETAS = {"codigo": "Código", "nombre": "Nombre", "descripcion": "Descripción", "precio": "Precio (PVP)",
              "familia": "Familia", "stock": "Stock", "imagen": "Imagen / Foto (ruta o URL)",
              "nif": "NIF / CIF", "email": "Email",
              "telefono": "Teléfono", "direccion": "Dirección", "fecha": "Fecha", "cantidad": "Cantidad",
              "importe": "Importe", "cuenta": "Cuenta contable", "debe": "Debe", "haber": "Haber",
              "saldo": "Saldo", "iban": "IBAN", "titular": "Titular", "bic": "BIC", "banco": "Banco"}
_ENTIDADES = (("Productos / Catálogo", _imp.PRODUCTOS), ("Clientes", _imp.CLIENTES),
              ("Proveedores", _imp.PROVEEDORES), ("Histórico de ventas", _imp.VENTAS_HIST),
              ("Saldos de apertura", _imp.SALDOS), ("Tesorería (cuentas)", _imp.TESORERIA))
_COMBO_SS = None   # se fija tras conocer T


def _combo():
    cb = QComboBox()
    cb.setStyleSheet(f"QComboBox{{background:{T.BG};color:{T.TEXT};border:1px solid {T.BORDE};"
                     "border-radius:8px;padding:5px 10px;min-width:220px;}")
    return cb


def _btn(txt, cb, *, primary=False):
    b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(38)
    if primary:
        b.setStyleSheet(f"QPushButton{{background:{T.INFO};color:{T.BG};border:none;border-radius:10px;"
                        "font-weight:900;padding:6px 18px;}"
                        f"QPushButton:hover{{background:{T.BG};color:{T.INFO};border:2px solid {T.INFO};}}")
    else:
        b.setStyleSheet(f"QPushButton{{background:transparent;color:{T.INFO};border:2px solid {T.INFO};"
                        "border-radius:10px;font-weight:900;padding:6px 18px;}"
                        f"QPushButton:hover{{background:{T.INFO};color:{T.BG};}}")
    b.clicked.connect(cb)
    return b


def _titulo(txt):
    lb = QLabel(txt); lb.setStyleSheet(f"color:{T.INFO};font-size:16px;font-weight:900;"); return lb


class _Asistente(QWidget):
    """Asistente de importación. Orquesta analizar → simular → ejecutar. `cargar_fichero(ruta)` permite
    ejercer el flujo sin el diálogo de archivo (pruebas)."""

    def __init__(self, usuario=None):
        super().__init__()
        self.usuario = usuario or {}
        self._ruta = None
        self._columnas = []
        self._muestra = []
        self._mapeo = {}
        self._mapeo_confirmado = None
        self._combos = {}
        self._entidad = _imp.PRODUCTOS
        ly = QVBoxLayout(self); ly.setContentsMargins(4, 4, 4, 4); ly.setSpacing(10)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._paso_archivo())     # 0
        self.stack.addWidget(self._paso_mapeo())        # 1
        self.stack.addWidget(self._paso_resumen())      # 2
        ly.addWidget(self.stack, 1)

    # ── Paso 1: archivo ──────────────────────────────────────────────────────
    def _paso_archivo(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(12)
        sub = QLabel("Formatos: CSV, TSV, TXT, Excel, JSON/JSONL, Parquet, XML (BMEcat), EDIFACT y volcados .sql. "
                     "Se cargan en los módulos reales sin recrear nada a mano.")
        sub.setStyleSheet(f"color:{T.DIM};"); sub.setWordWrap(True)
        self.cb_entidad = QComboBox()
        self.cb_entidad.setStyleSheet(f"QComboBox{{background:{T.BG};color:{T.TEXT};border:1px solid "
                                      f"{T.BORDE};border-radius:8px;padding:5px 10px;min-width:220px;}}")
        for etq, val in _ENTIDADES:
            self.cb_entidad.addItem(etq, val)
        et = QLabel("¿Qué vas a importar?"); et.setStyleSheet(f"color:{T.INFO};font-weight:700;")
        self.lbl_ruta = QLabel("Ningún fichero seleccionado."); self.lbl_ruta.setStyleSheet(f"color:{T.TEXT};")
        self.chk_ia = QCheckBox("Sugerir el mapeo con IA (si está disponible)")
        self.chk_ia.setStyleSheet(f"color:{T.TEXT};")
        fila = QHBoxLayout(); fila.addWidget(_btn("📂  Seleccionar fichero", self._seleccionar, primary=True))
        fila.addStretch()
        ly.addWidget(_titulo("1 · Elige qué importar y selecciona el fichero"))
        ly.addWidget(sub); ly.addWidget(et); ly.addWidget(self.cb_entidad)
        ly.addLayout(fila); ly.addWidget(self.lbl_ruta); ly.addWidget(self.chk_ia)
        ly.addStretch()
        return w

    # ── Paso 2: mapeo ────────────────────────────────────────────────────────
    def _paso_mapeo(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10)
        self._form_cont = QWidget(); self.form_map = QFormLayout(self._form_cont); self.form_map.setSpacing(8)
        fila = QHBoxLayout()
        fila.addWidget(_btn("◀ Atrás", lambda: self.stack.setCurrentIndex(0)))
        fila.addWidget(_btn("✨ Re-sugerir con IA", self._resugerir_ia))
        fila.addStretch()
        fila.addWidget(_btn("Simular ▶", self._simular, primary=True))
        ly.addWidget(_titulo("2 · Confirma el mapeo de columnas"))
        ly.addWidget(self._form_cont, 1); ly.addLayout(fila)
        return w

    def _construir_mapeo(self, entidad):
        """(Re)genera los combos de mapeo según los campos canónicos de la entidad elegida."""
        while self.form_map.rowCount():
            self.form_map.removeRow(0)
        self._combos = {}
        for campo, (req, _syn) in _modelo.CAMPOS.get(entidad, {}).items():
            cb = _combo()
            self._combos[campo] = cb
            et = QLabel(_ETIQUETAS.get(campo, campo) + (" *" if req else ""))
            et.setStyleSheet(f"color:{T.INFO if req else T.TEXT};font-weight:700;")
            self.form_map.addRow(et, cb)

    # ── Paso 3: resumen + importar ───────────────────────────────────────────
    def _paso_resumen(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10)
        self.txt_resumen = QTextEdit(); self.txt_resumen.setReadOnly(True)
        self.txt_resumen.setStyleSheet(f"QTextEdit{{background:{T.BG};color:{T.TEXT};border:1px solid "
                                       f"{T.BORDE};border-radius:8px;padding:8px;}}")
        fila = QHBoxLayout()
        fila.addWidget(_btn("◀ Atrás", lambda: self.stack.setCurrentIndex(1)))
        fila.addStretch()
        self.btn_importar = _btn("✅ Importar ahora", self._importar, primary=True)
        fila.addWidget(self.btn_importar)
        ly.addWidget(_titulo("3 · Revisión (simulación) e importación"))
        ly.addWidget(self.txt_resumen, 1); ly.addLayout(fila)
        return w

    # ── Lógica (orquestación del servicio) ───────────────────────────────────
    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _seleccionar(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Selecciona el fichero", "",
            "Datos (*.csv *.tsv *.txt *.xlsx *.json *.jsonl);;Todos los archivos (*)")
        if ruta:
            self.cargar_fichero(ruta)

    def cargar_fichero(self, ruta):
        self._ruta = ruta
        self._entidad = self.cb_entidad.currentData() or _imp.PRODUCTOS
        self.lbl_ruta.setText(os.path.basename(ruta))
        plan = _imp.analizar(ruta, entidad=self._entidad, usar_ia=self.chk_ia.isChecked())
        if not plan.get("ok"):
            self._aviso(plan.get("error", "No se pudo leer el fichero."), "error")
            return
        self._columnas = plan["columnas"]
        self._muestra = plan.get("muestra", [])
        self._mapeo = plan.get("mapeo_sugerido", {})
        self._construir_mapeo(self._entidad)
        self._pintar_combos()
        self.stack.setCurrentIndex(1)

    def _pintar_combos(self):
        for campo, cb in self._combos.items():
            cb.blockSignals(True); cb.clear(); cb.addItem("— (ninguna)", None)
            for col in self._columnas:
                cb.addItem(str(col), col)
            sel = self._mapeo.get(campo)
            idx = cb.findData(sel) if sel else 0
            cb.setCurrentIndex(idx if idx >= 0 else 0)
            cb.blockSignals(False)

    def _resugerir_ia(self):
        if not self._columnas:
            return
        self._mapeo = _imp.sugerir_mapeo_ia(self._columnas, self._entidad, muestra=self._muestra)
        self._pintar_combos()
        if not _imp.ia_disponible():
            self._aviso("IA no disponible (sin API). Se usa el mapeo heurístico.", "info")

    def _leer_mapeo(self):
        m = {}
        for campo, cb in self._combos.items():
            v = cb.currentData()
            if v:
                m[campo] = v
        return m

    def _simular(self):
        mapeo = self._leer_mapeo()
        faltan = [_ETIQUETAS.get(c, c) for c, (req, _s) in _modelo.CAMPOS.get(self._entidad, {}).items()
                  if req and c not in mapeo]
        if faltan:
            self._aviso(f"Debes asignar la(s) columna(s) obligatoria(s): {', '.join(faltan)}.")
            return
        inf = _imp.simular(self._ruta, mapeo, entidad=self._entidad, id_empresa=self._emp())
        if not inf.get("ok"):
            self._aviso(inf.get("error", "Error en la simulación."), "error")
            return
        self._mapeo_confirmado = mapeo
        r = inf["resumen"]
        txt = (f"Filas totales: {r['total']}\n"
               f"Válidas: {r['validas']}     ·     Con error: {r['con_error']}\n"
               f"Nuevos: {r['nuevos']}     ·     Actualizados: {r['actualizados']}\n"
               f"Con stock: {r['con_stock']}     ·     Con imagen: {r.get('con_imagen', 0)}\n"
               f"Familias detectadas: {', '.join(r['familias']) or '—'}\n")
        if inf.get("errores"):
            txt += "\nPrimeros errores:\n" + "\n".join(
                f"  · fila {e['fila']}: {e['motivo']}" for e in inf["errores"][:10])
        self.txt_resumen.setPlainText(txt)
        self.stack.setCurrentIndex(2)

    def _importar(self):
        mapeo = self._mapeo_confirmado or self._leer_mapeo()
        res = _imp.ejecutar(self._ruta, mapeo, entidad=self._entidad, id_empresa=self._emp(),
                            usuario=(self.usuario.get("nombre") or self.usuario.get("usuario")))
        if not res.get("ok"):
            self._aviso(res.get("error", "No se pudo importar."), "error")
            return
        if "familias_creadas" in res:
            extra = (f", {res['familias_creadas']} familia(s) nueva(s), {res.get('con_stock', 0)} con stock, "
                     f"{res.get('imagenes', 0)} imagen(es)")
        else:
            extra = f" ({res.get('creados', 0)} nuevos, {res.get('actualizados', 0)} actualizados)"
        self.txt_resumen.append(f"\n✅ Importado: {res['cargados']} registro(s){extra}.")
        self.btn_importar.setEnabled(False)
        self._aviso(f"Importación completada: {res['cargados']} registro(s).", "info")

    def _aviso(self, msg, tipo="warning"):
        if mostrar_mensaje:
            mostrar_mensaje(self, "Migración de datos", msg, tipo)
        else:  # pragma: no cover
            logger.info("migracion: %s", msg)


class MigracionDatosWindow(QtEnterpriseWindow):
    """Ventana Enterprise 'Migración de datos' (v_id 'migracion'). Aloja el asistente de importación."""

    titulo_ventana = "Migración de datos"
    concepto = None

    def _crear_pestanas(self):
        self.registrar_pestana("Importar catálogo", self._tab_importar, destacada=True)

    def _tab_importar(self):
        self.asistente = _Asistente(self.usuario)
        return self.asistente
