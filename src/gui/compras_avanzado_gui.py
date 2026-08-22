"""
Compras avanzado (CMP) — GUI de devoluciones, incidencias, evaluación de proveedores y
condiciones/homologación.

Pantalla NUEVA (no modifica `compras_gestion.py`). Expone las capacidades CMP.1/3/4/8 sin
tocar el flujo principal proveedor→pedido→recepción→factura. Multiempresa por contexto.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox,
                             QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from src.db import compras as C, proveedores as P
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _btn_x, _combo,
                                      _dialogo_frameless, _inp, _tabla)

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("compras.avanzado.gui")


def _it(v, centro=False):
    it = QTableWidgetItem("" if v is None else str(v))
    if centro:
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return it


class _DialogoDescuento(QDialog):
    """Editor de descuento frameless (sin barra de Windows, esquinas redondeadas, botones propios)."""

    def __init__(self, actual=0.0, parent=None):
        super().__init__(parent)
        self.setFixedSize(440, 250)
        v = _dialogo_frameless(self, titulo="Editar descuento", ancho=440)
        lab = QLabel("Descuento (%)")
        lab.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;")
        v.addWidget(lab)
        self.inp = _inp("0,00")
        try:
            self.inp.setText(f"{float(actual or 0):g}".replace(".", ","))
        except Exception:
            self.inp.setText("0")
        self.inp.selectAll()
        v.addWidget(self.inp)
        v.addStretch()
        bar = QHBoxLayout()
        bar.addWidget(_btn("Cancelar", self.reject))
        bar.addWidget(_btn("Aceptar", self.accept, primary=True))
        v.addLayout(bar)

    def valor(self):
        """Devuelve el porcentaje (0–100) o None si no es válido."""
        txt = (self.inp.text() or "").strip().replace(",", ".")
        try:
            val = float(txt)
        except ValueError:
            return None
        return val if 0 <= val <= 100 else None


class ComprasAvanzadoWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Compras avanzado")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        tabs = QTabWidget()
        # Contorno NEÓN turquesa alrededor del contenido (sustituye la línea gris del ::pane por defecto,
        # que no casa con el diseño de la app y se veía cortada).
        tabs.setStyleSheet(f"QTabWidget::pane{{border:2px solid {_CIAN};border-radius:12px;top:-1px;}}")
        tabs.addTab(self._tab_proveedores(), "Proveedores / Homologación")
        tabs.addTab(self._tab_devoluciones(), "Devoluciones")
        tabs.addTab(self._tab_incidencias(), "Incidencias")
        tabs.addTab(self._tab_evaluacion(), "Evaluación")
        tabs.addTab(self._tab_comparar(), "Comparar precios")
        root.addWidget(tabs)

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _aviso(self, titulo, mensaje, nivel="info"):
        """Feedback unificado (usa el diálogo estilizado de la app; degrada a QMessageBox)."""
        if mostrar_mensaje is not None:
            try:
                mostrar_mensaje(self, titulo, mensaje, nivel=nivel)
                return
            except Exception:
                pass
        (QMessageBox.information if nivel in ("info", "success") else QMessageBox.warning)(
            self, titulo, mensaje)

    def _puede(self, permiso) -> bool:
        try:
            from src.services import autorizacion
            return autorizacion.puede(self.usuario or {}, permiso, id_empresa=self._emp())
        except Exception:
            return True

    # ── Comparar precios (motores/lonjas del sector + margen objetivo) ─────────
    # Motores de búsqueda y comparadores especializados en Alimentación/Supermercado/Bakery.
    # `q=True` = admite término de búsqueda (se anexa a la URL); `q=False` = portal fijo.
    _COMPARADORES = [
        ("Google Shopping (Alimentación y Gran Consumo)",
         "https://www.google.com/search?tbm=shop&q=", True),
        ("Lonja / Mercado Central — Mercabarna",
         "https://www.mercabarna.es/es/", False),
        ("Lonja / Mercado Central — Mercamadrid",
         "https://www.mercamadrid.es/", False),
        ("Observatorio de Precios de Alimentos y Materias Primas (harinas, aceites, lácteos)",
         "https://www.mapa.gob.es/es/alimentacion/servicios/observatorio-de-precios-de-los-alimentos/",
         False),
        ("Directorios de Distribuidores de Alimentación",
         "https://www.google.com/search?q=distribuidores+mayoristas+alimentacion+", True),
    ]

    def _tab_comparar(self):
        """Centro de acceso a motores de búsqueda y comparadores de precios del sector (Alimentación /
        Supermercado / Bakery) + regla de Margen Objetivo (%) para el PVP dinámico en Pedidos. Sin APIs."""
        from src.db import compras_b2b as CFG
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10)
        cfg = CFG.obtener_config(self._emp())

        t = QLabel("🔎  Comparar precios de mercado")
        t.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:14px;")
        ly.addWidget(t)
        info = QLabel("Consulta precios de referencia en buscadores y lonjas del sector y ábrelos en tu "
                      "navegador. Smart Manager no conecta con APIs externas: la comparación es manual y el "
                      "coste real lo fija tu tarifa pactada con el proveedor.")
        info.setStyleSheet(f"color:{_DIM};background:transparent;font-size:11px;"); info.setWordWrap(True)
        ly.addWidget(info)

        fila = QHBoxLayout()
        c = QLabel("Motor / Lonja"); c.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;")
        self.cmp_motor = _combo([(lab, i) for i, (lab, _u, _q) in enumerate(self._COMPARADORES)])
        self.cmp_motor.setMinimumWidth(420); self.cmp_motor.view().setMinimumWidth(440)
        fila.addWidget(c); fila.addWidget(self.cmp_motor); fila.addStretch(1)
        ly.addLayout(fila)

        fila2 = QHBoxLayout()
        c2 = QLabel("Producto a buscar (opcional)")
        c2.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;")
        self.cmp_query = _inp("harina de trigo, aceite de oliva, leche…")
        fila2.addWidget(c2); fila2.addWidget(self.cmp_query, 1)
        ly.addLayout(fila2)

        bopen = QHBoxLayout()
        bopen.addWidget(_btn("🌐  Abrir comparador en navegador", self._abrir_comparador, primary=True))
        bopen.addStretch(1)
        ly.addLayout(bopen)

        t2 = QLabel("📈  PVP dinámico en pedidos")
        t2.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:14px;padding-top:8px;")
        ly.addWidget(t2)
        info2 = QLabel("El PVP sugerido se calcula al TRAMITAR un pedido como: Coste pactado × (1 + Margen / "
                       "100). Configura aquí el margen objetivo por defecto.")
        info2.setStyleSheet(f"color:{_DIM};background:transparent;font-size:11px;"); info2.setWordWrap(True)
        ly.addWidget(info2)
        rfila = QHBoxLayout()
        self.cmp_margen = _inp("30"); self.cmp_margen.setFixedWidth(100)
        self.cmp_margen.setText(f"{cfg.get('margen_objetivo_pct', 30):g}")
        cm = QLabel("Regla de Margen Objetivo (%)")
        cm.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;")
        rfila.addWidget(cm); rfila.addWidget(self.cmp_margen)
        rfila.addWidget(_btn("Supermercado (25%)", lambda: self.cmp_margen.setText("25"), primary=True))
        rfila.addWidget(_btn("Bakery / Frescos (35%)", lambda: self.cmp_margen.setText("35"), primary=True))
        rfila.addStretch(1)
        ly.addLayout(rfila)

        bar = QHBoxLayout()
        bar.addWidget(_btn("Guardar margen", self._guardar_margen, primary=True))
        bar.addStretch(1)
        ly.addLayout(bar)
        ly.addStretch(1)
        return w

    def _abrir_comparador(self):
        """Abre en el navegador del sistema el comparador seleccionado (anexando el término si procede)."""
        from urllib.parse import quote_plus

        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        idx = self.cmp_motor.currentData() or 0
        _lab, url, admite_q = self._COMPARADORES[int(idx)]
        q = (self.cmp_query.text() or "").strip()
        destino = f"{url}{quote_plus(q)}" if (admite_q and q) else url
        if not QDesktopServices.openUrl(QUrl(destino)):
            self._aviso("Comparar precios", "No se pudo abrir el navegador.", "warning")

    def _guardar_margen(self):
        if not self._puede("compras.editar"):
            self._aviso("Comparar precios", "Permiso requerido: compras.editar", "warning"); return
        try:
            margen = float((self.cmp_margen.text() or "30").replace(",", "."))
        except ValueError:
            self._aviso("Comparar precios", "El margen debe ser numérico.", "warning"); return
        from src.db import compras_b2b as CFG
        ok = CFG.guardar_config(margen_objetivo_pct=margen, id_empresa=self._emp())
        self._aviso("Comparar precios",
                    "Margen objetivo guardado." if ok else "No se pudo guardar el margen.",
                    "success" if ok else "error")

    def _tabla_kv(self):
        """Tabla de 2 columnas (Parámetro · Valor) centrada, con el estilo estándar de la app.
        Su altura se ajusta al contenido (ver `_llenar_kv`) para que el borde inferior quede pegado
        a la última fila (sin espacio vacío)."""
        t = _tabla(["Parámetro", "Valor"])
        t.setMinimumWidth(440); t.setMaximumWidth(560)
        return t

    @staticmethod
    def _llenar_kv(tabla, filas):
        tabla.setRowCount(len(filas))
        for i, (k, val) in enumerate(filas):
            tabla.setItem(i, 0, _it(k, centro=True))
            tabla.setItem(i, 1, _it(val, centro=True))
        # Ajusta la altura EXACTA al contenido → borde inferior a ras de la última fila (sin hueco).
        # Altura = cabecera + suma real de filas (verticalHeader().length()) + los 2 bordes del marco.
        hcab = tabla.horizontalHeader().height() or tabla.horizontalHeader().sizeHint().height()
        tabla.setFixedHeight(hcab + tabla.verticalHeader().length() + 2 * tabla.frameWidth())

    def _provs(self):
        return [(f"{p['razon_social']} ({p.get('cif_nif') or ''})", p["id_proveedor"])
                for p in P.listar_proveedores(self._emp())]

    # ── Proveedores / Homologación / Condiciones ──────────────────────────────
    def _tab_proveedores(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.cmb_prov = _combo(self._provs() or [("(sin proveedores)", None)])
        ly.addWidget(self.cmb_prov)
        b = QHBoxLayout()
        b.addWidget(_btn("Aprobar (homologar)", lambda: self._homolog("aprobado"), primary=True))
        b.addWidget(_btn("Suspender", lambda: self._homolog("suspendido"), primary=True))
        b.addWidget(_btn("Editar descuento", self._set_descuento, primary=True))
        b.addWidget(_btn("Bloquear", lambda: self._homolog("bloqueado"), danger=True))
        b.addStretch()
        ly.addLayout(b)
        self.tbl_cond = self._tabla_kv()
        ly.addSpacing(48)
        fila = QHBoxLayout(); fila.addStretch(); fila.addWidget(self.tbl_cond); fila.addStretch()
        ly.addLayout(fila); ly.addStretch()
        self.cmb_prov.currentIndexChanged.connect(self._refresca_cond)
        self._refresca_cond()
        return w

    def _refresca_cond(self):
        pid = self.cmb_prov.currentData()
        if not pid:
            self.tbl_cond.setRowCount(0); return
        c = P.condiciones_comerciales(pid, self._emp())
        self._llenar_kv(self.tbl_cond, [
            ("Descuento", f"{c.get('descuento')} %"),
            ("Plazo de pago", f"{c.get('plazo_pago')} días"),
            ("Lead time", f"{c.get('lead_time_dias')} días"),
            ("Homologado", "Sí" if c.get("homologado") else "No"),
            ("Bloqueado", "Sí" if c.get("bloqueado") else "No"),
        ])

    def _homolog(self, estado):
        pid = self.cmb_prov.currentData()
        if not pid:
            self._aviso("Homologación", "Selecciona un proveedor antes de realizar esta acción.", "info")
            return
        etiquetas = {"aprobado": ("homologado (aprobado)", "success"),
                     "suspendido": ("suspendido", "warning"),
                     "bloqueado": ("bloqueado", "warning")}
        txt, nivel = etiquetas.get(estado, (estado, "info"))
        try:
            ok = C.set_homologacion_estado(pid, estado, self._emp())
        except Exception as e:
            logger.exception("set_homologacion_estado")
            self._aviso("Homologación", f"No se pudo actualizar el estado: {e}", "error")
            return
        if ok:
            self._refresca_cond()
            self._aviso("Homologación", f"Proveedor {txt} correctamente.", nivel)
        else:
            self._aviso("Homologación", "No se pudo actualizar el estado del proveedor.", "error")

    def _set_descuento(self):
        pid = self.cmb_prov.currentData()
        if not pid:
            self._aviso("Descuento", "Selecciona un proveedor antes de editar su descuento.", "info")
            return
        try:
            actual = float(P.condiciones_comerciales(pid, self._emp()).get("descuento") or 0)
        except Exception:
            actual = 0.0
        dlg = _DialogoDescuento(actual, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        val = dlg.valor()
        if val is None:
            self._aviso("Descuento", "Introduce un porcentaje válido (entre 0 y 100).", "warning")
            return
        try:
            P.actualizar_proveedor(pid, id_empresa=self._emp(), descuento=val)
        except Exception as e:
            logger.exception("actualizar_descuento")
            self._aviso("Descuento", f"No se pudo guardar el descuento: {e}", "error")
            return
        self._refresca_cond()
        self._aviso("Descuento", f"Descuento actualizado a {val:g} %.", "success")

    # ── Devoluciones ──────────────────────────────────────────────────────────
    def _tab_devoluciones(self):
        w = QWidget(); ly = QVBoxLayout(w)
        f = QHBoxLayout()
        self.cmb_prov_dev = _combo(self._provs() or [("(sin proveedores)", None)])
        self.in_cod_dev = _inp("Código"); self.in_cod_dev.setFixedWidth(140)
        self.in_cant_dev = _inp("Cantidad"); self.in_cant_dev.setFixedWidth(90)
        self.in_lote_dev = _inp("Lote (opc.)"); self.in_lote_dev.setFixedWidth(110)
        for ww in (QLabel("Proveedor:"), self.cmb_prov_dev, self.in_cod_dev, self.in_cant_dev,
                   self.in_lote_dev):
            if isinstance(ww, QLabel):
                ww.setStyleSheet(f"color:{_DIM};")
            f.addWidget(ww)
        f.addWidget(_btn("Devolver", self._devolver, primary=True))
        ly.addLayout(f)
        self.tbl_dev = _tabla(["ID", "Proveedor", "Total", "Estado", "Fecha"])
        ly.addWidget(self.tbl_dev)
        self._carga_dev()
        return w

    def _carga_dev(self):
        data = C.listar_devoluciones(self._emp())
        self.tbl_dev.setRowCount(len(data))
        for i, d in enumerate(data):
            for j, v in enumerate([d.get("id_devolucion"), d.get("id_proveedor"),
                                   d.get("total"), d.get("estado"), d.get("fecha")]):
                self.tbl_dev.setItem(i, j, _it(v))

    def _devolver(self):
        pid = self.cmb_prov_dev.currentData()
        cod = self.in_cod_dev.text().strip()
        try:
            cant = int(self.in_cant_dev.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Devolución", "Cantidad no válida."); return
        if not cod:
            QMessageBox.information(self, "Devolución", "Indica el código."); return
        did = C.crear_devolucion(id_proveedor=pid,
                                 lineas=[{"codigo": cod, "cantidad": cant,
                                          "lote": self.in_lote_dev.text().strip() or None}],
                                 usuario=(self.usuario or {}).get("nombre"), id_empresa=self._emp())
        if did:
            self.in_cod_dev.clear(); self.in_cant_dev.clear(); self.in_lote_dev.clear()
            self._carga_dev()
        else:
            QMessageBox.warning(self, "Devolución", "No se pudo registrar la devolución.")

    # ── Incidencias ───────────────────────────────────────────────────────────
    def _tab_incidencias(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_inc = _tabla(["ID", "Tipo", "Artículo", "Cantidad", "Estado", "Fecha"])
        ly.addWidget(self.tbl_inc)
        ly.addWidget(_btn("🔄  Actualizar", self._carga_inc, primary=True))
        self._carga_inc()
        return w

    def _carga_inc(self):
        data = C.listar_incidencias(self._emp())
        self.tbl_inc.setRowCount(len(data))
        for i, d in enumerate(data):
            for j, v in enumerate([d.get("id"), d.get("tipo"), d.get("codigo_articulo"),
                                   d.get("cantidad"), d.get("estado"), d.get("fecha")]):
                self.tbl_inc.setItem(i, j, _it(v))

    # ── Evaluación ────────────────────────────────────────────────────────────
    def _tab_evaluacion(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.cmb_prov_eval = _combo(self._provs() or [("(sin proveedores)", None)])
        ly.addWidget(self.cmb_prov_eval)
        ly.addWidget(_btn("Evaluar proveedor", self._kpis, primary=True))
        self.tbl_kpis = self._tabla_kv()
        ly.addSpacing(48)
        fila = QHBoxLayout(); fila.addStretch(); fila.addWidget(self.tbl_kpis); fila.addStretch()
        ly.addLayout(fila); ly.addStretch()
        return w

    def _kpis(self):
        pid = self.cmb_prov_eval.currentData()
        if not pid:
            self._aviso("Evaluación", "Selecciona un proveedor antes de evaluarlo.", "info")
            return
        try:
            k = C.calcular_kpis_proveedor(pid, self._emp())
        except Exception as e:
            logger.exception("calcular_kpis_proveedor")
            self._aviso("Evaluación", f"No se pudo calcular la evaluación: {e}", "error")
            return
        self._llenar_kv(self.tbl_kpis, [
            ("Valoración global", str(k["valoracion_global"])),
            ("Incidencias", str(k["incidencias"])),
            ("Rechazos", str(k["rechazos"])),
            ("Devoluciones", str(k["devoluciones"])),
            ("Pedidos recibidos", str(k["pedidos_recibidos"])),
        ])
        C.registrar_evaluacion(pid, id_empresa=self._emp())
        self._aviso("Evaluación", "Evaluación calculada y registrada.", "success")
