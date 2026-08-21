"""
Compras avanzado (CMP) — GUI de devoluciones, incidencias, evaluación de proveedores y
condiciones/homologación.

Pantalla NUEVA (no modifica `compras_gestion.py`). Expone las capacidades CMP.1/3/4/8 sin
tocar el flujo principal proveedor→pedido→recepción→factura. Multiempresa por contexto.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
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
        tabs.addTab(self._tab_proveedores(), "Proveedores / Homologación")
        tabs.addTab(self._tab_devoluciones(), "Devoluciones")
        tabs.addTab(self._tab_incidencias(), "Incidencias")
        tabs.addTab(self._tab_evaluacion(), "Evaluación")
        tabs.addTab(self._tab_b2b(), "Integración B2B y Reglas de Precios")
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

    # ── Integración B2B y Reglas de Precios ───────────────────────────────────
    def _tab_b2b(self):
        """Credenciales del conector B2B + reglas del monitor/motor de precios. Secretos cifrados (Fernet);
        guardar exige permiso `compras.editar`. Mantiene el tema oscuro/cyan del resto del módulo."""
        from src.db import compras_b2b as B2BDB
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10)
        cfg = B2BDB.obtener_config(self._emp())

        def _cap(txt):
            lab = QLabel(txt); lab.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;")
            ly.addWidget(lab); return lab

        t = QLabel("🔌  Conector B2B externo (Consentio / Choco / REST)")
        t.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:14px;")
        ly.addWidget(t)
        fila = QHBoxLayout()
        self.b2b_prov = _combo([("REST genérico", "rest"), ("Simulado (pruebas)", "simulado")],
                               actual=cfg.get("proveedor"))
        self.b2b_entorno = _combo([("Sandbox", "sandbox"), ("Producción", "produccion")],
                                  actual=cfg.get("entorno"))
        for lab, wdg in (("Conector", self.b2b_prov), ("Entorno", self.b2b_entorno)):
            c = QLabel(lab); c.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;")
            fila.addWidget(c); fila.addWidget(wdg)
        fila.addStretch(1)
        ly.addLayout(fila)

        _cap("Endpoint base (URL de la API)")
        self.b2b_endpoint = _inp("https://api.tu-proveedor-b2b.com/v1")
        self.b2b_endpoint.setText(cfg.get("endpoint") or "")
        ly.addWidget(self.b2b_endpoint)
        _cap("API Key (se guarda cifrada · vacío = no cambiar)")
        self.b2b_key = _inp(""); self.b2b_key.setEchoMode(QLineEdit.EchoMode.Password)
        ly.addWidget(self.b2b_key)
        _cap("API Secret (se guarda cifrada · vacío = no cambiar)")
        self.b2b_secret = _inp(""); self.b2b_secret.setEchoMode(QLineEdit.EchoMode.Password)
        ly.addWidget(self.b2b_secret)

        t2 = QLabel("📈  Reglas de precios (monitor de desvíos + precio dinámico)")
        t2.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:14px;padding-top:6px;")
        ly.addWidget(t2)
        rfila = QHBoxLayout()
        self.b2b_umbral = _inp("10"); self.b2b_umbral.setFixedWidth(90)
        self.b2b_umbral.setText(f"{cfg.get('umbral_variacion_pct', 10):g}")
        self.b2b_margen = _inp("30"); self.b2b_margen.setFixedWidth(90)
        self.b2b_margen.setText(f"{cfg.get('margen_objetivo_pct', 30):g}")
        for lab, wdg in (("Umbral de alerta de variación (%)", self.b2b_umbral),
                         ("Margen objetivo por defecto (%)", self.b2b_margen)):
            c = QLabel(lab); c.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;")
            rfila.addWidget(c); rfila.addWidget(wdg)
        rfila.addStretch(1)
        ly.addLayout(rfila)

        est = "✓ credenciales configuradas" if cfg.get("api_key") else "— sin credenciales"
        self.b2b_estado = QLabel(f"Estado: {est}")
        self.b2b_estado.setStyleSheet(f"color:{_TEXT};background:transparent;font-size:12px;")
        ly.addWidget(self.b2b_estado)
        nota = QLabel("Las credenciales se guardan cifradas (Fernet) y no se muestran. Guardar requiere "
                      "permiso de edición de compras.")
        nota.setStyleSheet(f"color:{_DIM};background:transparent;font-size:11px;"); nota.setWordWrap(True)
        ly.addWidget(nota)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Guardar configuración", self._guardar_b2b, primary=True))
        bar.addStretch(1)
        ly.addLayout(bar)
        ly.addStretch(1)
        return w

    def _guardar_b2b(self):
        if not self._puede("compras.editar"):
            self._aviso("Integración B2B", "Permiso requerido: compras.editar", "warning"); return
        try:
            umbral = float((self.b2b_umbral.text() or "10").replace(",", "."))
            margen = float((self.b2b_margen.text() or "30").replace(",", "."))
        except ValueError:
            self._aviso("Integración B2B", "Umbral y margen deben ser numéricos.", "warning"); return
        from src.db import compras_b2b as B2BDB
        ok = B2BDB.guardar_config(
            proveedor=self.b2b_prov.currentData(), entorno=self.b2b_entorno.currentData(),
            endpoint=self.b2b_endpoint.text().strip(),
            api_key=(self.b2b_key.text().strip() or None),
            api_secret=(self.b2b_secret.text().strip() or None),
            umbral_variacion_pct=umbral, margen_objetivo_pct=margen, id_empresa=self._emp())
        if ok:
            self.b2b_key.clear(); self.b2b_secret.clear()
            self._aviso("Integración B2B", "Configuración B2B y reglas de precios guardadas.", "success")
        else:
            self._aviso("Integración B2B", "No se pudo guardar la configuración.", "error")

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
